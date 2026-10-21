"""离线测试：不需要 AutoCAD、不需要 PyYAML。

覆盖 P1 骨架里最容易出错的四处：
1. registry 能载入并通过自检（含"dead 必须写替代"这条规则）
2. 环境快照的形状与 profile 判定（用假 app 对象，不碰 COM）
3. 环境漂移检测（进程/.sv$/系统变量）
4. CLI 的离线子命令返回码（selftest / registry / status 在无 AutoCAD 时）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acadkit import registry, status  # noqa: E402
from acadkit.core import env  # noqa: E402


# ── 1) registry ────────────────────────────────────────────────────
def test_registry_loads_and_validates() -> None:
    data = registry.load()
    assert data["capabilities"], "registry 不能为空"
    assert not registry.validate(data), registry.validate(data)


def test_registry_counts_match_header() -> None:
    c = registry.counts()
    assert c["total"] == c["verified"] + c["usable_unjudged"] + c["pending"] + c["dead"]
    assert c["verified"] > 0 and c["dead"] > 0


def test_dead_entries_have_alternatives() -> None:
    for c in registry.by_status("dead"):
        assert "替代" in str(c.get("judge", "")), "%s 缺替代方案" % c["id"]


def test_every_verified_has_judge_text() -> None:
    for c in registry.by_status("verified"):
        assert str(c.get("judge", "")).strip(), "%s 没有判据" % c["id"]


# ── 2) 环境快照（假 app，不碰 COM）──────────────────────────────────
class FakeDoc:
    def GetVariable(self, name):
        return {"CPROFILE": "<<VANILLA>>", "TRUSTEDPATHS": "",
                "SECURELOAD": "1"}.get(name, "0")


class FakeApp:
    Version = "25.0s (LMS Tech)"
    Documents = type("D", (), {"Count": 1})()
    ActiveDocument = FakeDoc()


def test_snapshot_shape_and_profile() -> None:
    snap = env.snapshot(FakeApp(), temp_dir=str(ROOT))
    assert snap["running"] is True
    assert snap["version"].startswith("25.0")
    assert snap["documents"] == 1
    assert env.profile_ok(snap) is True
    assert snap["variables"]["CPROFILE"] == "<<VANILLA>>"


def test_profile_rejects_acade() -> None:
    class DocA(FakeDoc):
        def GetVariable(self, name):
            return "<<ACADE>>" if name == "CPROFILE" else super().GetVariable(name)

    class AppA(FakeApp):
        ActiveDocument = DocA()

    snap = env.snapshot(AppA(), temp_dir=str(ROOT))
    assert env.profile_ok(snap) is False


def test_snapshot_without_autocad() -> None:
    snap = env.snapshot(None, temp_dir=str(ROOT))
    assert snap["running"] is False
    assert env.profile_ok(snap) is None      # 读不到 ≠ 合规
    assert snap["variables"] == {}


# ── 3) 漂移检测 ────────────────────────────────────────────────────
def test_diff_detects_variable_and_count_changes() -> None:
    a = {"running": True, "process_count": 1, "sv_count": 0,
         "variables": {"CPROFILE": "<<VANILLA>>", "TRUSTEDPATHS": ""}}
    b = {"running": True, "process_count": 2, "sv_count": 3,
         "variables": {"CPROFILE": "<<ACADE>>", "TRUSTEDPATHS": "C:/x"}}
    d = env.diff(a, b)
    assert "process_count" in d and "sv_count" in d
    assert "var:CPROFILE" in d and "var:TRUSTEDPATHS" in d


def test_diff_clean_when_identical() -> None:
    a = {"running": True, "process_count": 1, "sv_count": 0,
         "variables": {"CPROFILE": "<<VANILLA>>"}}
    assert env.diff(a, a) == {}


# ── 4) status 在无 AutoCAD 时不许失败，也不许启动它 ────────────────
def test_status_without_autocad_is_ok(monkeypatch) -> None:
    monkeypatch.setattr(status.com, "attach_or_none", lambda: None)
    monkeypatch.setattr(status.env, "read_baseline", lambda: None)
    report, code = status.collect(compare_baseline=True)
    assert code == 0, report
    assert report["snapshot"]["running"] is False
    assert report["checks"]["profile_ok"] is None      # SKIP 而不是 FAIL
    assert "未运行" in status.render(report)


def test_status_rejects_wrong_profile(monkeypatch) -> None:
    class DocA(FakeDoc):
        def GetVariable(self, name):
            return "<<ACADE>>" if name == "CPROFILE" else super().GetVariable(name)

    class AppA(FakeApp):
        ActiveDocument = DocA()

    monkeypatch.setattr(status.com, "attach_or_none", lambda: AppA())
    monkeypatch.setattr(status.env, "_proc_count", lambda name="acad": 1)
    monkeypatch.setattr(status.env, "read_baseline", lambda: None)
    report, code = status.collect(compare_baseline=True)
    assert code == 4, report
    assert any("profile" in p for p in report["problems"])


def test_cli_offline_returncodes() -> None:
    from acadkit.cli.main import main

    assert main(["selftest"]) == 0
    assert main(["registry"]) == 0

# ── 5) clean_quit：三个坑都要覆盖（不启动 AutoCAD，用假对象）────────
class FakeDoc2:
    def __init__(self, name, saved):
        self.Name = name
        self.Saved = saved
        self.saved_called = False

    def Save(self):
        self.saved_called = True
        self.Saved = True


class _Docs:
    def __init__(self, docs):
        self._docs = docs

    @property
    def Count(self):
        return len(self._docs)

    def Item(self, i):
        return self._docs[i]


class FakeApp2:
    """刻意不支持枚举（模拟晚绑定下 Documents 不可遍历）。"""

    def __init__(self, docs):
        self.Documents = _Docs(docs)
        self.quit_called = False

    def Quit(self):
        self.quit_called = True


def test_clean_quit_marks_unsaved_and_polls_exit() -> None:
    from acadkit.core import com

    unsaved = FakeDoc2("Drawing1.dwg", saved=False)
    app = FakeApp2([unsaved])
    # 第一次数到 1（还在关），第二次数到 0（已退出）
    counts = iter([1, 0])
    orig = com._proc_count
    com._proc_count = lambda name="acad": next(counts, 0)
    try:
        res = com.clean_quit(app, save=False, wait_s=5)
    finally:
        com._proc_count = orig
    assert res["ok"] is True
    assert res["process_exited"] is True
    assert app.quit_called is True
    # 未保存的文档必须被标记为已保存（丢弃修改），否则 Quit 会弹模态
    assert unsaved.Saved is True


def test_clean_quit_uses_index_not_enumeration() -> None:
    """FakeApp2 不支持 __iter__；能跑通就说明走的是索引。"""
    from acadkit.core import com

    app = FakeApp2([FakeDoc2("a.dwg", True), FakeDoc2("b.dwg", True)])
    orig = com._proc_count
    com._proc_count = lambda name="acad": 0
    try:
        res = com.clean_quit(app, save=True, wait_s=1)
    finally:
        com._proc_count = orig
    assert res["ok"] is True
    assert len(res["documents"]) == 2
    assert res["process_exited"] is True