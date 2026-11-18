"""长驻命令队列（对照 CADCraft `apps/cadcraft/src/control_server.rs`）。

为什么需要：每跑一条能力就启一次 AutoCAD 要 15–20s，批量场景下这是纯浪费。
这里给一个**按行 JSON 的请求/响应协议**，进程常驻、命令排队，错误也走同一协议
（永远返回结构化结果，不因为一条命令失败就断开连接）。

协议（每行一个 JSON）：
  请求  {"id": "1", "tool": "geom_circle", "params": {...}}
  响应  {"id": "1", "ok": true, "checks": {...}, "detail": {...}}
  错误  {"id": "1", "ok": false, "error": "...", "kind": "busy", "retryable": true}

本模块不碰 COM：执行器由调用方注入（`executor(tool, params) -> dict`），
所以可以离线测协议本身。
"""

from __future__ import annotations

import io
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

Executor = Callable[[str, Dict[str, Any]], Dict[str, Any]]


class ProtocolError(ValueError):
    pass


def parse_request(line: str) -> Dict[str, Any]:
    """解析一行请求；坏 JSON / 缺字段都抛 ProtocolError（带位置信息）。"""
    line = line.strip()
    if not line:
        raise ProtocolError("空行")
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError("不是合法 JSON（第 %d 列）：%s" % (exc.colno, exc.msg)) from None
    if not isinstance(obj, dict):
        raise ProtocolError("请求必须是对象")
    if "tool" not in obj:
        raise ProtocolError("缺 tool 字段")
    if "params" in obj and not isinstance(obj["params"], dict):
        raise ProtocolError("params 必须是对象")
    return {"id": str(obj.get("id", "")), "tool": str(obj["tool"]),
            "params": obj.get("params") or {}}


def response_ok(req: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": req.get("id", ""), "ok": bool(payload.get("ok")),
            "checks": payload.get("checks") or {},
            "detail": payload.get("detail") or {}}


def response_error(req: Dict[str, Any], message: str, *,
                   kind: str = "unknown", retryable: bool = False) -> Dict[str, Any]:
    return {"id": req.get("id", ""), "ok": False, "error": message,
            "kind": kind, "retryable": retryable}


def handle_line(line: str, executor: Executor) -> Dict[str, Any]:
    """处理一行：**任何异常都转成响应**，绝不抛给调用方。"""
    try:
        req = parse_request(line)
    except ProtocolError as exc:
        return response_error({"id": ""}, str(exc), kind="protocol")
    try:
        payload = executor(req["tool"], req["params"])
        if not isinstance(payload, dict):
            raise ProtocolError("执行器返回的不是对象")
    except Exception as exc:                                  # noqa: BLE001
        from ..core.diag import classify

        d = classify(exc)
        return response_error(req, d.raw, kind=d.kind, retryable=d.retryable)
    return response_ok(req, payload)


def serve(stream_in: io.TextIOBase, stream_out: io.TextIOBase,
          executor: Executor, *, max_requests: Optional[int] = None) -> int:
    """按行服务；返回处理过的请求数。EOF 正常退出。"""
    served = 0
    while max_requests is None or served < max_requests:
        line = stream_in.readline()
        if not line:
            break
        resp = handle_line(line, executor)
        stream_out.write(json.dumps(resp, ensure_ascii=False) + "\n")
        stream_out.flush()
        served += 1
    return served


@dataclass
class Queue:
    """进程内队列（同一进程里串行执行，避免多请求并发抢 AutoCAD）。"""

    executor: Executor
    results: List[Dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def submit(self, tool: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        req = {"id": str(len(self.results) + 1), "tool": tool,
               "params": params or {}}
        with self._lock:
            resp = handle_line(json.dumps(req, ensure_ascii=False), self.executor)
            self.results.append(resp)
            return resp

    def stats(self) -> Dict[str, Any]:
        ok = sum(1 for r in self.results if r.get("ok"))
        kinds: Dict[str, int] = {}
        for r in self.results:
            if not r.get("ok"):
                kinds[r.get("kind", "unknown")] = kinds.get(r.get("kind", "unknown"), 0) + 1
        return {"total": len(self.results), "ok": ok,
                "failed": len(self.results) - ok, "error_kinds": kinds}
