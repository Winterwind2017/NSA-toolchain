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
