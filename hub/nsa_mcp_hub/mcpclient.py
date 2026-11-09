"""极简 MCP stdio 客户端：把已有的 MCP 服务器当后端复用（代理适配器用）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

from .jsonrpc import log


class ChildMcp:
    """启动一个 MCP 子进程并串行转发请求。"""

    def __init__(self, argv: list, name: str, env_extra: dict | None = None,
                 cwd: str | None = None):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env.update(env_extra or {})
        self.name = name
        self._lock = threading.Lock()
        self._next_id = 0
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", env=env, cwd=cwd)

    # -- 协议 ---------------------------------------------------------------
    def _send(self, payload: dict) -> None:
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _read(self) -> dict:
        line = self.proc.stdout.readline()
        if not line:
            err = ""
            try:
                err = (self.proc.stderr.read() or "")[-800:]
            except Exception:                        # noqa: BLE001
                pass
            raise RuntimeError("%s 子进程无响应（退出码 %s）：%s"
                               % (self.name, self.proc.poll(), err))
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        with self._lock:
            self._next_id += 1
            self._send({"jsonrpc": "2.0", "id": self._next_id,
                        "method": method, "params": params or {}})
            msg = self._read()
        if "error" in msg:
            raise RuntimeError("%s RPC 错误：%s"
                               % (self.name, json.dumps(msg["error"], ensure_ascii=False)))
        return msg["result"]

    def notify(self, method: str, params: dict | None = None) -> None:
        with self._lock:
            self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    # -- 常用操作 -----------------------------------------------------------
    def initialize(self, timeout_hint: str = "") -> dict:
        result = self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "nsa-mcp-hub-proxy", "version": timeout_hint or "0"},
        })
        self.notify("notifications/initialized")
        return result

    def list_tools(self) -> list:
        return self.request("tools/list").get("tools") or []

    def call_tool(self, name: str, args: dict) -> dict:
        return self.request("tools/call", {"name": name, "arguments": args or {}})

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except Exception:                            # noqa: BLE001
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:                            # noqa: BLE001
            try:
                self.proc.kill()
            except Exception:                        # noqa: BLE001
                pass
        log("%s 子进程已关闭" % self.name)


def unwrap(result: dict) -> tuple[dict, bool]:
    """把 tools/call 的 MCP 包装拆成 (结构化载荷, 是否错误)。"""
    payload = result.get("structuredContent")
    is_error = bool(result.get("isError"))
    if isinstance(payload, dict):
        return payload, is_error
    text = ""
    for block in result.get("content") or []:
        if block.get("type") == "text":
            text += block.get("text") or ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, is_error
    except Exception:                                # noqa: BLE001
        pass
    return {"text": text[:4000]}, is_error
