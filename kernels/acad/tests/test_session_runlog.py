"""快照恢复与结构化日志的离线测试。"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.core.runlog import RunLog, read_events, summarize          # noqa: E402
from acadkit.session import (SnapshotError, load_manifest, restore,     # noqa: E402
                             save_snapshot, sha256_file, verify_snapshot)


def _setup() -> tuple:
    d = tempfile.mkdtemp(prefix="snap_")
    f1 = os.path.join(d, "a.dwg")
    f2 = os.path.join(d, "b.dxf")
    with open(f1, "wb") as fh:
        fh.write(b"AC1032" + b"\x00" * 100)
    with open(f2, "wb") as fh:
        fh.write(b"0\nSECTION\n0\nEOF\n")
    return d, f1, f2


def test_snapshot_and_restore_roundtrip() -> None:
    d, f1, f2 = _setup()
    root = os.path.join(d, "snaps")
    man = save_snapshot(root, [f1, f2], note="改图前")
    mpath = man["manifest"]
    assert os.path.isfile(mpath)
    assert verify_snapshot(mpath)["ok"]

    before = sha256_file(f1)
    with open(f1, "wb") as fh:
        fh.write(b"BROKEN")
    assert sha256_file(f1) != before

    out = restore(mpath)
    assert out["count"] == 2
    assert sha256_file(f1) == before, "还原后内容必须逐字节一致"


def test_verify_detects_corrupt_snapshot() -> None:
    d, f1, _ = _setup()
    man = save_snapshot(os.path.join(d, "snaps"), [f1])
    mpath = man["manifest"]
    copy = os.path.join(os.path.dirname(mpath), "a.dwg")
    with open(copy, "wb") as fh:
        fh.write(b"tampered")
    check = verify_snapshot(mpath)
    assert not check["ok"] and "sha256" in check["problems"][0]


def test_restore_refuses_broken_snapshot() -> None:
    d, f1, _ = _setup()
    man = save_snapshot(os.path.join(d, "snaps"), [f1])
    mpath = man["manifest"]
    with open(os.path.join(os.path.dirname(mpath), "a.dwg"), "wb") as fh:
        fh.write(b"tampered")
    try:
        restore(mpath)
    except SnapshotError as exc:
        assert "损坏" in str(exc)
    else:
        raise AssertionError("快照坏了不该硬还原")


def test_snapshot_requires_files() -> None:
    d = tempfile.mkdtemp(prefix="snap2_")
    try:
        save_snapshot(os.path.join(d, "s"), [os.path.join(d, "missing.dwg")])
    except SnapshotError as exc:
        assert "没有可快照" in str(exc)
    else:
        raise AssertionError("空快照应报错")


def test_manifest_is_readable_json() -> None:
    d, f1, _ = _setup()
    man = save_snapshot(os.path.join(d, "snaps"), [f1], note="说明")
    payload = load_manifest(man["manifest"])
    assert payload["note"] == "说明"
    assert payload["files"][0]["name"] == "a.dwg"
    assert len(payload["files"][0]["sha256"]) == 64


def test_runlog_writes_jsonl_and_summarizes() -> None:
    d = tempfile.mkdtemp(prefix="log_")
    path = os.path.join(d, "run.jsonl")
    with RunLog(path, case="geom.circle") as log:
        log.info("start", params={"radius": 5})
        log.error(RuntimeError("弹出了模态对话框"), kind="cap_failed")
        log.warn("slow", seconds=12.5)

    events = read_events(path)
    assert len(events) == 3
    assert events[1]["error_kind"] == "modal"
    assert events[1]["retryable"] is False
    assert events[0]["case"] == "geom.circle"

    s = summarize(path)
    assert s["total"] == 3 and s["has_errors"]
    assert s["by_level"]["error"] == 1


def test_runlog_survives_corrupt_line() -> None:
    d = tempfile.mkdtemp(prefix="log2_")
    path = os.path.join(d, "run.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"ok": 1}\n')
        fh.write("not json\n")
    events = read_events(path)
    assert events[0]["ok"] == 1
    assert events[1]["kind"] == "corrupt_line"


def test_summarize_missing_file_is_empty() -> None:
    s = summarize(os.path.join(tempfile.gettempdir(), "nope_zzz.jsonl"))
    assert s["total"] == 0 and not s["has_errors"]
