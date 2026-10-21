"""离线测试：不启动 NX，不 import NXOpen。"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from nxkit import caps, judges, protocol  # noqa: E402


def test_caps_unique_and_named() -> None:
    ids = [c.id for c in caps.CAPS]
    assert len(ids) == len(set(ids))
    for c in caps.CAPS:
        assert c.id and c.action and c.expect, c
        assert c.level.startswith("L")


def _sample(expect: dict) -> dict:
    """把 {min,max} 区间换成中点，其余原样。"""
    out = {}
    for key, val in expect.items():
        if isinstance(val, dict) and {"min", "max"} <= set(val):
            out[key] = (val["min"] + val["max"]) / 2.0
        else:
            out[key] = val
    return out


def test_judge_accepts_expected() -> None:
    for c in caps.CAPS:
        checks = judges.compare(_sample(c.expect), c.expect)
        assert judges.verdict(checks), (c.id, [x for x in checks if not x["ok"]])


def test_judge_rejects_wrong_number() -> None:
    for c in caps.CAPS:
        bad = _sample(c.expect)
        for key, val in c.expect.items():
            if isinstance(val, dict) and {"min", "max"} <= set(val):
                bad[key] = val["max"] * 2 + 1
                break
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                bad[key] = val * 2 + 1
                break
        else:
            continue
        assert not judges.verdict(judges.compare(bad, c.expect)), c.id


def test_judge_record_requires_reopen() -> None:
    c = caps.get("file.roundtrip")
    rec = {"ok": True, "reads": {"volume_mm3": 100000.0}, "errors": []}
    out = judges.judge_record(c, rec)
    assert not out["ok"], "缺 volume_reopened 时必须失败"


def test_protocol_roundtrip(tmp_path) -> None:
    p = os.path.join(str(tmp_path), "x.json")
    protocol.write_json(p, {"a": 1})
    assert protocol.read_json(p) == {"a": 1}
    job = protocol.new_job(str(tmp_path), [], ROOT)
    assert job["schema"] == protocol.SCHEMA


def test_actions_exist_for_every_cap() -> None:
    """动作名必须在 runtime 里存在；只做文本检查，避免 import NXOpen。"""
    src = os.path.join(ROOT, "src", "nxkit", "runtime", "actions.py")
    text = open(src, encoding="utf-8").read()
    for c in caps.CAPS:
        assert ("def %s(" % c.action) in text, c.action
        assert ('"%s": %s,' % (c.action, c.action)) in text, (
            "%s 没登记进 ACTIONS（会导致整会话 0 通过）" % c.action)


def test_every_cap_declares_license() -> None:
    for c in caps.CAPS:
        assert c.license, c.id
        assert c.license in {"gateway", "solid_modeling", "drafting", "assemblies"}


def test_license_dat_parses() -> None:
    """本机有 .dat 时必须能解析出 feature；没有则跳过（不误报）。"""
    from nxkit import license as lic

    info = lic.summary()
    if not info["readable"]:
        import pytest

        pytest.skip("本机没有可读的 SPLM .dat")
    assert info["count"] > 1000
    for need in ("gateway", "solid_modeling", "drafting", "assemblies"):
        assert lic.has(need), need
