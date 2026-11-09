"""把 Kit 装配成 MCP 服务器：initialize / tools/list / tools/call。"""

from __future__ import annotations

import os
import sys

import threading
import time

from . import __version__, jsonrpc
from .jsonrpc import INVALID_PARAMS, RpcError, log
from .tools import (Kit, call_tool, cancel_request, forget_request,
                    text_result, tool_listing)


def build_handlers(kit: Kit) -> dict:
    def initialize(params: dict) -> dict:
        requested = params.get("protocolVersion")
        protocol = (requested if requested in jsonrpc.SUPPORTED_PROTOCOLS
                    else jsonrpc.DEFAULT_PROTOCOL)
        log("initialize client=%r protocol=%s tools=%d"
            % ((params.get("clientInfo") or {}).get("name"), protocol, len(kit.tools)))
        caps = {"tools": {"listChanged": False}}
        return {
            "protocolVersion": protocol,
            "capabilities": caps,
            "serverInfo": {"name": "nsa-mcp-hub-%s" % kit.key, "version": __version__},
            "instructions": kit.instructions or
            ("%s 自动化内核：每条能力执行后都会回读并给出判据（checks）。"
             % kit.name),
        }

    def tools_list(_params: dict) -> dict:
        return {"tools": tool_listing(kit)}

    def tools_call(params: dict) -> dict:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise RpcError(INVALID_PARAMS, "tools/call 需要 name")
        args = params.get("arguments") or {}
        req_id = jsonrpc.current_request()

        # 进度：客户端在 _meta.progressToken 里给了 token 就按 2 s 一拍报活，
        # 让 agent 知道"gx 那条 120 s 还在跑"，而不是以为挂了。
        meta = params.get("_meta") or {}
        token = meta.get("progressToken")
        stop = threading.Event()
        ticker = None
        if token is not None:
            def beat() -> None:
                started = time.time()
                n = 0
                while not stop.wait(2.0):
                    n += 1
                    try:
                        jsonrpc.notify("notifications/progress", {
                            "progressToken": token, "progress": n,
                            "elapsed_s": round(time.time() - started, 1),
                            "message": "%s 执行中" % name})
                    except Exception:              # noqa: BLE001
                        return
            ticker = threading.Thread(target=beat, daemon=True)
            ticker.start()
        try:
            payload = call_tool(kit, name, args, req_id=req_id)
        finally:
            stop.set()
            if ticker is not None:
                ticker.join(timeout=1.0)
            forget_request(req_id)
        if payload.get("cancelled"):
            payload = dict(payload)
            payload["errors"] = list(payload.get("errors") or []) + ["请求已被客户端取消"]
            payload["ok"] = False
        return text_result(payload)

    def ping(_params: dict) -> dict:
        return {}

    return {
        "initialize": initialize,
        "notifications/initialized": lambda _p: None,
        "notifications/cancelled": lambda p: cancel_request(
            (p or {}).get("requestId")) or None,
        "tools/list": tools_list,
        "tools/call": tools_call,
        "ping": ping,
        "logging/setLevel": lambda _p: {},
    }


def run_server(kit: Kit) -> int:
    # NSA_MCP_HUB_DUMP_STACKS=<秒> → 周期性把全部线程栈打到 stderr（排查"卡住"用）
    _every = os.environ.get("NSA_MCP_HUB_DUMP_STACKS")
    if _every:
        import faulthandler
        try:
            faulthandler.dump_traceback_later(int(float(_every)), repeat=True)
        except Exception:                           # noqa: BLE001
            pass
    log("启动 nsa-mcp-hub-%s（%s v%s，%d 个工具）"
        % (kit.key, kit.name, kit.version, len(kit.tools)))
    try:
        # 工具仍在**主线程**顺序执行（COM/UI 生态对线程敏感，实测线程派发会让
        # AutoCAD 的 COM 调用卡死）；取消通知由 jsonrpc 的读线程就地处理，
        # 所以"能取消"和"执行语义不变"两件事同时成立。
        return jsonrpc.serve(build_handlers(kit), on_cancelled=cancel_request)
    except KeyboardInterrupt:
        return 0
    except BrokenPipeError:
        return 0
    finally:
        try:
            sys.stdout.flush()
        except Exception:                             # noqa: BLE001
            pass
