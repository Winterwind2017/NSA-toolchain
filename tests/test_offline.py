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


def test_judge_accepts_expected() -> None:
    for c in caps.CAPS:
        checks = judges.compare(dict(c.expect), c.expect)
        assert judges.verdict(checks), (c.id, [x for x in checks if not x["ok"]])


def test_judge_rejects_wrong_number() -> None:
    for c in caps.CAPS:
        bad = dict(c.expect)
        for key, val in bad.items():
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
