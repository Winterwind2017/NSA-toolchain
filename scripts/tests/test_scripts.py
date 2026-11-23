"""仓库级脚本测试（doctor / install_skills）。放在 scripts/tests，独立于内核测试。"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
ROOT = os.path.dirname(SCRIPTS)


def load(name: str):
    """按路径加载脚本模块（scripts/ 不是包）。"""
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location("nsa_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


doctor = load("doctor")
installer = load("install_skills")


# ── doctor ──────────────────────────────────────────────────────────
class FakeProbes:
    KIT_PKGS = ("acadkit", "swkit", "nxkit", "gxkit", "codesyskit", "autoshopkit")

    def __init__(self, *, pkgs=("cadquery", "yaml", "pytest"), missing_pkg=(),
                 engine=None, running=False, exists=True):
        pkgs = tuple(pkgs) + self.KIT_PKGS
        self.pkgs = set(pkgs)
        self.missing_pkg = set(missing_pkg)
        self.engine = engine
        self.running = running
        self._exists = exists

    def importable(self, pkg, path):
        return pkg in self.pkgs and pkg not in self.missing_pkg

    def any_path(self, paths):
        return self.engine

    def process_running(self, name):
        return self.running

    def exists(self, path):
        return self._exists


def test_doctor_all_green() -> None:
    spec = doctor.KitSpec("acad", "acadkit", "acad.exe", ("C:/x/acad.exe",),
                          "ww-autocad-automation")
    rep = doctor.diagnose([spec], FakeProbes(engine="C:/x/acad.exe", running=True))
    assert not rep.failures, [c.message for c in rep.failures]
    assert "可开工" in rep.to_text()


def test_doctor_detects_missing_package() -> None:
    spec = doctor.KitSpec("acad", "acadkit", "", (), "")
    rep = doctor.diagnose([spec], FakeProbes(missing_pkg=("acadkit",)),
                          root=ROOT)
    fails = [c for c in rep.failures if "包" in c.area]
    assert fails, "缺 acadkit 应判 FAIL"
    assert "PYTHONPATH" in fails[0].next_step or "pip install" in fails[0].next_step


def test_doctor_missing_engine_is_fail_but_unregistered_is_skip() -> None:
    with_paths = doctor.KitSpec("sw", "swkit", "SLDWORKS.exe", ("C:/nope/SLDWORKS.exe",), "")
    no_paths = doctor.KitSpec("gx", "gxkit", "GDK.exe", (), "")
    rep = doctor.diagnose([with_paths, no_paths], FakeProbes(engine=None))
    eng = {c.area: c for c in rep.checks if "引擎" in c.area}
    assert eng["sw 引擎"].level == "FAIL"
    assert eng["gx 引擎"].level == "SKIP", "没登记路径的只能标 SKIP，不能假装通过"


def test_doctor_process_not_running_is_warn_only() -> None:
    spec = doctor.KitSpec("acad", "acadkit", "acad.exe", ("C:/x/acad.exe",), "")
    rep = doctor.diagnose([spec], FakeProbes(engine="C:/x/acad.exe", running=False))
    proc = [c for c in rep.checks if "进程" in c.area][0]
    assert proc.level == "WARN" and "启动" in proc.next_step
    assert not rep.failures


def test_doctor_json_shape() -> None:
    spec = doctor.KitSpec("acad", "acadkit", "", (), "")
    payload = doctor.diagnose([spec], FakeProbes()).to_dict()
    assert {"ok", "counts", "checks"} <= set(payload)
    assert payload["checks"][0]["level"] in ("OK", "WARN", "FAIL", "SKIP")


# ── install_skills ──────────────────────────────────────────────────
def _mini_skills(tmp: str) -> dict:
    """造两个假技能，避免依赖真实 skills/ 内容。"""
    out = {}
    for name in ("alpha", "beta"):
        d = os.path.join(tmp, "src", name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: %s\n---\nbody\n" % name)
        with open(os.path.join(d, "capabilities.json"), "w", encoding="utf-8") as fh:
            fh.write('{"verified": []}')
        os.makedirs(os.path.join(d, "__pycache__"), exist_ok=True)
        with open(os.path.join(d, "__pycache__", "x.pyc"), "wb") as fh:
            fh.write(b"\x00")
        out[name] = d
    return out


def test_install_copies_and_skips_pycache() -> None:
    tmp = tempfile.mkdtemp(prefix="inst_")
    skills = _mini_skills(tmp)
    target = os.path.join(tmp, "target")
    out = installer.install(target, skills)
    assert len(out["done"]) == 2
    for name in skills:
        assert os.path.isfile(os.path.join(target, name, "SKILL.md"))
        assert not os.path.isdir(os.path.join(target, name, "__pycache__")), \
            "__pycache__ 不该被复制"
    manifest = json.load(open(os.path.join(target, installer.MANIFEST), encoding="utf-8"))
    assert set(manifest["skills"]) == {"alpha", "beta"}
    assert len(manifest["skills"]["alpha"]["sha256"]) == 64


def test_install_is_idempotent_and_dry_run_writes_nothing() -> None:
    tmp = tempfile.mkdtemp(prefix="inst2_")
    skills = _mini_skills(tmp)
    target = os.path.join(tmp, "target")

    plan = installer.install(target, skills, dry_run=True)
    assert plan["dry_run"] and not os.path.exists(target), "演练不许写盘"

    first = installer.install(target, skills)
    second = installer.install(target, skills)
    assert len(first["done"]) == len(second["done"]) == 2


def test_update_only_touches_registered_files() -> None:
    tmp = tempfile.mkdtemp(prefix="inst3_")
    skills = _mini_skills(tmp)
    target = os.path.join(tmp, "target")
    installer.install(target, skills)

    # 目标里改 SKILL.md、并放一个用户自己的文件
    skill_md = os.path.join(target, "alpha", "SKILL.md")
    with open(skill_md, "w", encoding="utf-8") as fh:
        fh.write("本地改过\n")
    mine = os.path.join(target, "alpha", "my-notes.md")
    with open(mine, "w", encoding="utf-8") as fh:
        fh.write("用户自己的\n")

    out = installer.install(target, skills, update=True)
    assert {d["skill"] for d in out["done"]} == {"alpha", "beta"}
    assert "name: alpha" in open(skill_md, encoding="utf-8").read(), "SKILL.md 应被更新"
    assert os.path.isfile(mine), "用户文件不许被动"


def test_update_skips_skills_not_installed() -> None:
    tmp = tempfile.mkdtemp(prefix="inst4_")
    skills = _mini_skills(tmp)
    target = os.path.join(tmp, "empty")
    out = installer.install(target, skills, update=True)
    assert out["done"] == []
    assert set(out["skipped"]) == {"alpha", "beta"}


def test_discover_only_dirs_with_skill_md() -> None:
    tmp = tempfile.mkdtemp(prefix="inst5_")
    os.makedirs(os.path.join(tmp, "with"), exist_ok=True)
    open(os.path.join(tmp, "with", "SKILL.md"), "w").close()
    os.makedirs(os.path.join(tmp, "without"), exist_ok=True)
    found = installer.discover(tmp)
    assert list(found) == ["with"]


# ── 技能安装状态（fresh / modified / stale / missing / extra）────────
def test_status_fresh_then_modified_then_stale() -> None:
    tmp = tempfile.mkdtemp(prefix="st_")
    skills = _mini_skills(tmp)
    target = os.path.join(tmp, "target")
    installer.install(target, skills)

    st = installer.status(target, skills)
    assert st["fresh"] is True
    assert st["counts"]["fresh"] == 2

    # 目标里的文件被本地改过 → modified（不是 stale）
    with open(os.path.join(target, "alpha", "SKILL.md"), "a", encoding="utf-8") as fh:
        fh.write("local edit\n")
    st2 = installer.status(target, skills)
    assert st2["fresh"] is False
    assert st2["counts"]["modified"] == 1

    installer.install(target, skills)          # 重装回 fresh
    assert installer.status(target, skills)["fresh"] is True

    # 仓库侧改了（清单里还是旧哈希）→ stale
    with open(os.path.join(skills["beta"], "SKILL.md"), "a", encoding="utf-8") as fh:
        fh.write("v2\n")
    st3 = installer.status(target, skills)
    assert st3["counts"]["stale"] == 1
    assert st3["fresh"] is False


def test_status_detects_missing_and_extra() -> None:
    import shutil
    tmp = tempfile.mkdtemp(prefix="st2_")
    skills = _mini_skills(tmp)
    target = os.path.join(tmp, "target")
    installer.install(target, skills)

    shutil.rmtree(os.path.join(target, "alpha"))
    st = installer.status(target, skills)
    assert st["counts"]["missing"] == 1

    # 目标里多出一个仓库没有的技能 → extra（不判失败，但要报出来）
    mp = os.path.join(target, installer.MANIFEST)
    data = json.load(open(mp, encoding="utf-8"))
    data["skills"]["ghost"] = {"sha256": "0" * 64, "files": 1, "mode": "install"}
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    st2 = installer.status(target, skills)
    assert st2["extra_in_target"] == ["ghost"]
    assert st2["fresh"] is False


# ── nsa 统一入口 ──────────────────────────────────────────────────
def _nsa(*args):
    """跑 nsa 子进程：强制 UTF-8，否则中文输出在 GBK 控制台下解码失败（stdout 变 None）。"""
    import subprocess
    nsa = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nsa.py")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, nsa] + list(args), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=180, env=env)


def test_nsa_version_and_help() -> None:
    res = _nsa("version")
    assert res.returncode == 0, res.stderr
    assert "nsa-toolchain" in res.stdout
    assert "FEA" in res.stdout

    res = _nsa("help")
    assert res.returncode == 0
    assert "nsa doctor" in res.stdout
    assert "nsa fea" in res.stdout


def test_nsa_fea_translates_case() -> None:
    """nsa fea bar 必须翻译成 --case bar（少这步会报“参数错误”退出 2）。"""
    res = _nsa("fea", "bar", "--length", "100", "--width", "10", "--height", "10",
               "--force", "10000", "--nu", "0")
    assert res.returncode in (0, 1), res.stdout + res.stderr   # 1 = 超差，2 = 参数错
    assert "相对误差" in res.stdout or "结论" in res.stdout


def test_nsa_rejects_bad_command() -> None:
    assert _nsa().returncode == 2
    res = _nsa("bogus")
    assert res.returncode == 2
    assert "未知命令" in res.stderr
    assert _nsa("skills", "bogus").returncode == 2


def test_nsa_skills_status_passthrough() -> None:
    """nsa 转发的是真实 scripts/install_skills.py，所以这里装真实技能表。"""
    tmp = tempfile.mkdtemp(prefix="nsa_")
    skills = installer.discover()            # 仓库里的 7 个技能
    assert skills, "仓库里应该有技能"
    target = os.path.join(tmp, "target")
    installer.install(target, skills)

    res = _nsa("skills", "status", "--target", target)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "fresh=%d" % len(skills) in res.stdout

    # 目标里被改一个 → 退出码变 1
    name = sorted(skills)[0]
    with open(os.path.join(target, name, "SKILL.md"), "a", encoding="utf-8") as fh:
        fh.write("edited\n")
    assert _nsa("skills", "status", "--target", target).returncode == 1

    empty = os.path.join(tmp, "empty")
    os.makedirs(empty, exist_ok=True)
    assert _nsa("skills", "status", "--target", empty).returncode == 1


# ── doctor 里的技能状态行 ─────────────────────────────────────────
def test_doctor_reports_skill_install_state() -> None:
    tmp = tempfile.mkdtemp(prefix="dr_")
    skills = _mini_skills(tmp)
    target = os.path.join(tmp, "target")
    installer.install(target, skills)

    rep = doctor.diagnose(doctor.KITS[:1], probes=FakeProbes(exists=True),
                          skills_target=target, skills_map=skills)
    rows = [c for c in rep.checks if c.area == "技能安装"]
    assert rows and rows[0].level == "OK", [c.to_dict() for c in rows]

    empty = os.path.join(tmp, "empty")
    os.makedirs(empty, exist_ok=True)
    rep2 = doctor.diagnose(doctor.KITS[:1], probes=FakeProbes(exists=True),
                           skills_target=empty, skills_map=skills)
    rows2 = [c for c in rep2.checks if c.area == "技能安装"]
    assert rows2 and rows2[0].level == "SKIP", rows2[0].to_dict()


def test_doctor_kernel_rows_use_repo_root() -> None:
    """回归：cad-viewer 那段曾用局部变量 root，覆盖了 diagnose(root=...)，
    导致所有内核都被判成“没有 kernels/<name>/src”。"""
    name = doctor.KITS[0].name
    rep = doctor.diagnose(doctor.KITS[:1], probes=doctor.Probes())
    rows = [c for c in rep.checks if c.area.startswith(name + " ")]
    assert rows, [c.to_dict() for c in rep.checks]
    assert not any(c.level == "SKIP" for c in rows), [c.to_dict() for c in rows]
    assert not any("没有 kernels/" in c.message for c in rows), [c.to_dict() for c in rows]
    pkg = [c for c in rows if c.area == name + " 包"][0]
    assert pkg.level == "OK", pkg.to_dict()


def test_doctor_warns_when_dirs_exist_without_manifest() -> None:
    """有技能目录但没有清单（老版本装的）应 WARN 而不是 SKIP。"""
    import shutil
    tmp = tempfile.mkdtemp(prefix="dr3_")
    skills = _mini_skills(tmp)
    target = os.path.join(tmp, "target")
    installer.install(target, skills)
    os.remove(os.path.join(target, installer.MANIFEST))     # 模拟没有清单

    rep = doctor.diagnose(doctor.KITS[:1], probes=FakeProbes(exists=True),
                          skills_target=target, skills_map=skills)
    row = [c for c in rep.checks if c.area == "技能安装"][0]
    assert row.level == "WARN", row.to_dict()
    assert "没有安装清单" in row.message
    assert "skills install" in row.next_step


def test_doctor_warns_on_stale_skills() -> None:
    tmp = tempfile.mkdtemp(prefix="dr2_")
    skills = _mini_skills(tmp)
    target = os.path.join(tmp, "target")
    installer.install(target, skills)
    with open(os.path.join(target, "alpha", "SKILL.md"), "a", encoding="utf-8") as fh:
        fh.write("edited\n")

    rep = doctor.diagnose(doctor.KITS[:1], probes=FakeProbes(exists=True),
                          skills_target=target, skills_map=skills)
    row = [c for c in rep.checks if c.area == "技能安装"][0]
    assert row.level == "WARN"
    assert "modified=1" in row.message
    assert "nsa.py skills" in row.next_step
