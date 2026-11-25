"""筋、焊件、形位公差框、窗口预览的离线判据。不启动 SolidWorks。"""

from __future__ import annotations

import os

from swkit.api.advanced import SolidWorksAdvanced
from swkit.preview import choose_window, write_bmp
from swkit.registry import REGISTRY
from swkit.verified.gtol_frame import apply_frame
from swkit.verified.rib import judge_rib
from swkit.verified.weldment import judge_feature, structural_member


class _Doc:
    def __init__(self):
        self.features = []

    def __iter__(self):
        return iter(self.features)


class _Feat:
    def __init__(self, kind):
        self.kind = kind

    def GetTypeName2(self):
        return self.kind

    def Name(self):
        return self.kind


def test_registry_splits_live_results_from_open_gaps():
    verified = ("sw_insert_weldment", "sw_structural_member", "sw_spur_gear",
                "sw_sprocket", "sw_preview_frame", "sw_preview_burst")
    for name in verified:
        entry = REGISTRY[name]
        assert entry.status == "verified"
        assert entry.implemented is True
        assert "33.4.1" in entry.evidence
    for name in ("sw_rib", "sw_weldment_cut_list", "sw_gtol_frame"):
        entry = REGISTRY[name]
        assert entry.status == "unverified"
        assert entry.implemented is False
        assert entry.evidence


def test_rib_judge_needs_type_and_volume():
    good = judge_rib(4, 5, 1000.0, 1200.0, ["Rib"])
    assert all(good.values())
    no_volume = judge_rib(4, 5, 1000.0, 1000.0, ["Rib"])
    assert no_volume["volume_up"] is False
    wrong_type = judge_rib(4, 5, 1000.0, 1200.0, ["Boss"])
    assert wrong_type["type_is_rib"] is False


def test_weldment_refuses_missing_profile_and_fake_cut_list(tmp_path):
    doc = type("Doc", (), {})()
    missing = structural_member(doc, str(tmp_path / "no-such.sldlfp"))
    assert missing["ok"] is False
    assert missing["checks"]["profile_exists"] is False

    added = judge_feature(2, 4, ["WeldmentFeature"], "weldment")
    assert added["feature_added"] and added["type_matches"]

    class Empty:
        def FirstFeature(self):
            return None

    # read_cut_list uses iter_features, which needs FirstFeature/GetNextFeature.
    # 这里只锁住高层 API：没有文档时示例类不再编方管。
    listed = SolidWorksAdvanced(type("App", (), {"_log": lambda *a, **k: None})()).weldment_cut_list()
    assert listed == []
    assert not os.path.exists(str(tmp_path / "no-such.sldlfp"))


def test_gtol_frame_reads_back_and_rejects_projected_zone():
    class Gtol:
        def __init__(self):
            self.values = None
            self.symbols = None

        def SetFrameValues(self, frame, tol1, tol2, d1, d2, d3):
            self.values = [tol1, tol2, d1, d2, d3]

        def GetFrameValues(self, frame):
            return list(self.values)

        def SetFrameSymbols2(self, frame, gcs, *rest):
            self.symbols = [gcs]

        def GetFrameSymbols3(self, frame):
            return list(self.symbols)

    ok = apply_frame(Gtol(), "0.1", "A", gcs="b")
    assert ok["ok"] is True
    assert ok["checks"]["frame_readback"] is True
    blocked = apply_frame(Gtol(), "0.1", "A", projected_zone=True)
    assert blocked["ok"] is False
    assert blocked["checks"]["projected_zone"] is False


def test_preview_rejects_desktop_and_writes_bmp(tmp_path):
    windows = [
        {"hwnd": 1, "title": "Program Manager", "process": r"C:\Windows\explorer.exe"},
        {"hwnd": 99, "title": "零件1 - SOLIDWORKS", "process": r"D:\SOLIDWORKS\SLDWORKS.exe"},
    ]
    chosen, reason = choose_window(windows, desktop_hwnd=1)
    assert reason == ""
    assert chosen["hwnd"] == 99
    none, reason = choose_window(
        [{"hwnd": 1, "title": "SOLIDWORKS", "process": "explorer.exe"}], desktop_hwnd=1)
    assert none is None

    path = tmp_path / "one.bmp"
    write_bmp(str(path), 2, 2, [b"\x00\x00\xff" * 2, b"\xff\x00\x00" * 2])
    assert path.read_bytes()[:2] == b"BM"
