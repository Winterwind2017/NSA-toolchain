"""Agent 工具面与命令队列的离线测试（不需要 AutoCAD）。"""

from __future__ import annotations

import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit import registry                                            # noqa: E402
from acadkit.agent import tools as T                                    # noqa: E402
from acadkit.agent.queue import (Queue, handle_line, parse_request,     # noqa: E402
                                 serve)


# ── 工具面 ──────────────────────────────────────────────────────────
def test_only_verified_tools_are_listed() -> None:
    data = registry.load()
    verified = {c["id"] for c in data["capabilities"] if c.get("status") == "verified"}
    listed = {spec.capability_id for spec in T.list_tools()}
    assert listed <= verified, "未验证的能力不该出现在工具列表里"
    assert "geom.circle" in listed


def test_schema_reflects_default_param_types() -> None:
    spec = T.find("geom.circle")
    props = spec.schema["properties"]
    assert props["radius"]["type"] == "number"
    assert props["center"]["type"] == "array"


def test_unknown_tool_raises_with_hint() -> None:
    try:
        T.find("no.such.tool")
    except T.ToolError as exc:
        assert "list_tools" in str(exc)
    else:
        raise AssertionError("未知工具应抛 ToolError")


def test_validate_rejects_wrong_type() -> None:
    try:
        T.validate("geom.circle", {"radius": "abc"})
    except T.ToolError as exc:
        assert "radius" in str(exc) and "number" in str(exc)
    else:
        raise AssertionError("类型错应抛 ToolError")


def test_validate_rejects_unknown_param() -> None:
    try:
        T.validate("geom.circle", {"radiu": 5})
    except T.ToolError as exc:
        assert "不认识" in str(exc)
    else:
        raise AssertionError("未知参数应抛 ToolError")


def test_validate_rejects_non_finite() -> None:
    try:
        T.validate("geom.circle", {"radius": float("nan")})
    except T.ToolError as exc:
        assert "非有限" in str(exc)
    else:
        raise AssertionError("NaN 应被拒")


def test_dispatch_without_doc_reports_error_envelope() -> None:
    """没有文档对象时，错误也要变成结构化信封而不是崩。"""
    env = T.dispatch("geom.circle", {"center": (0, 0, 0), "radius": 5}, doc=None)
    assert env["ok"] is False
    assert env["error"] and env["kind"]


def test_tools_dumps_is_json() -> None:
    payload = json.loads(T.dumps(T.list_tools()))
    assert payload and {"name", "description", "inputSchema"} <= set(payload[0])


# ── 队列协议 ────────────────────────────────────────────────────────
def test_parse_request_ok() -> None:
    req = parse_request('{"id": 7, "tool": "geom_circle", "params": {"radius": 5}}')
    assert req["id"] == "7" and req["tool"] == "geom_circle"
    assert req["params"] == {"radius": 5}


def test_parse_request_rejects_bad_input() -> None:
    for line in ("", "{", '{"id":1}', '{"tool":"x","params":3}'):
        try:
            parse_request(line)
        except Exception as exc:                              # noqa: BLE001
            assert "Protocol" in type(exc).__name__
        else:
            raise AssertionError("应拒绝：%r" % line)


def test_handle_line_success_and_failure() -> None:
    def executor(tool: str, params: dict) -> dict:
        if tool == "boom":
            raise RuntimeError("弹出了模态对话框")
        return {"ok": True, "checks": {"c": True}, "detail": {"x": 1}}

    ok = handle_line('{"id":"1","tool":"geom_circle","params":{}}', executor)
    assert ok["ok"] and ok["checks"] == {"c": True}

    bad = handle_line('{"id":"2","tool":"boom"}', executor)
    assert bad["ok"] is False and bad["kind"] == "modal"


def test_protocol_error_keeps_connection() -> None:
    resp = handle_line("{not json", lambda t, p: {"ok": True})
    assert resp["ok"] is False and resp["kind"] == "protocol"


def test_serve_processes_lines_and_counts() -> None:
    src = io.StringIO('{"id":"1","tool":"a"}\n{"id":"2","tool":"b"}\n')
    dst = io.StringIO()
    n = serve(src, dst, lambda t, p: {"ok": True, "checks": {}, "detail": {}})
    assert n == 2
    lines = [json.loads(ln) for ln in dst.getvalue().strip().split("\n")]
    assert [ln["id"] for ln in lines] == ["1", "2"]
    assert all(ln["ok"] for ln in lines)


def test_serve_respects_max_requests() -> None:
    src = io.StringIO('{"id":"1","tool":"a"}\n{"id":"2","tool":"b"}\n')
    dst = io.StringIO()
    assert serve(src, dst, lambda t, p: {"ok": True}, max_requests=1) == 1


def test_queue_stats_aggregate_errors() -> None:
    def executor(tool: str, params: dict) -> dict:
        if tool == "bad":
            raise PermissionError("拒绝访问")
        return {"ok": True}

    q = Queue(executor=executor)
    q.submit("good")
    q.submit("bad")
    stats = q.stats()
    assert stats["total"] == 2 and stats["ok"] == 1 and stats["failed"] == 1
    assert stats["error_kinds"].get("permission") == 1
