"""nsa-mcp-hub：把六个 kit 服务器聚合成**一个** MCP 端点。

为什么不在一个进程里直接 build 六个 kit：
* 六家都是 COM / UI 自动化内核（AutoCAD、SolidWorks、NX、GX Works3、CODESYS、AutoShop），
  同进程共存会互相污染 COM 单元、UIA 焦点和崩溃域——隔离到子进程是刻意的设计。
* hub 只做**路由 + 聚合**：按工具名前缀找到属主 kit，转发 `tools/call`，
  透传 `notifications/progress`，把 `notifications/cancelled` 转给对应子进程。

约定：
* 工具名已经是 `<kit>_<verb>` 前缀，所以路由就是最长前缀匹配；
* hub 自己只多给一个工具 `nsa_hub_status`（各 kit 是否存活、工具数、最近错误）；
* 子进程 stderr 由**排空线程**接住（否则管道写满会把子进程卡住——这是踩过的坑）。
"""

from __future__ import annotations

import collections
import json
import os
import subprocess
import sys
import threading
import time

from . import __version__, jsonrpc
from .jsonrpc import INVALID_PARAMS, RpcError, log

HUB_KEY = "nsa-mcp-hub"
HUB_NAME = "nsa-mcp-hub（六个 CAD/PLC 自动化 kit 的聚合网关）"

# 顺序即启动顺序：轻的先起，重的（gx 拉 GX Works3）最后
KITS: dict[str, str] = {
    "codesys": "nsa_mcp_hub.servers.codesys_mcp",
    "autoshop": "nsa_mcp_hub.servers.autoshop_mcp",
    "acad": "nsa_mcp_hub.servers.acad_mcp",
    "nx": "nsa_mcp_hub.servers.nx_mcp",
    # CAD-Agent-Hub 补进来的两块：nxkit 没有的 CAM/机床/钣金，以及 CATIA 整块
    "ug": "nsa_mcp_hub.servers.ug_mcp",
    "catia": "nsa_mcp_hub.servers.catia_mcp",
    # EPLAN 电气设计整块（上游 MCP/EPLAN，67 个工具）
    "eplan": "nsa_mcp_hub.servers.eplan_mcp",
    "sw": "nsa_mcp_hub.servers.sw_mcp",
    "gx": "nsa_mcp_hub.servers.gx_mcp",
}
PREFIXES = tuple(sorted((k + "_" for k in KITS), key=len, reverse=True))


def owner_of(tool_name: str) -> str | None:
    for prefix in PREFIXES:
        if tool_name.startswith(prefix):
            return prefix[:-1]
    return None


class KitProcess:
    """一条到某个 kit 服务器的 stdio JSON-RPC 连接。"""

    def __init__(self, key: str, module: str):
        self.key = key
        self.module = module
        self.proc: subprocess.Popen | None = None
        self.alive = False
        self.error: str | None = None
        self.tools: list[dict] = []
        self.started_at: float | None = None
        self._lock = threading.Lock()          # 同一时刻只允许一个调用在飞
        self._pending: dict[int, dict] = {}
        self._next_id = 1
        self._stderr: collections.deque[str] = collections.deque(maxlen=200)
        self.on_notify = None                  # 由 hub 注入：转发子进程的通知
        self.wire = {"hub_req": None, "child_req": None}

    # ---- 生命周期 -------------------------------------------------------
    def start(self, timeout: float = 90.0) -> None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"]
                                    if env.get("PYTHONPATH") else "")
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", self.module],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            env=env, cwd=root)
        threading.Thread(target=self._read_loop, daemon=True,
                         name="hub-read-%s" % self.key).start()
        threading.Thread(target=self._drain_stderr, daemon=True,
                         name="hub-err-%s" % self.key).start()
        self.request("initialize", {
            "protocolVersion": jsonrpc.DEFAULT_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": HUB_KEY, "version": __version__},
        }, timeout=timeout)
        self.notify("notifications/initialized", {})
        listing = self.request("tools/list", {}, timeout=timeout)
        self.tools = list(listing.get("tools") or [])
        self.alive = True
        self.started_at = time.time()
        log("hub 已接上 %s（%d 个工具）" % (self.key, len(self.tools)))

    def stop(self) -> None:
        self.alive = False
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
        except Exception:                              # noqa: BLE001
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:                              # noqa: BLE001
            try:
                self.proc.kill()
            except Exception:                          # noqa: BLE001
                pass

    # ---- 传输 -----------------------------------------------------------
    def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                log("hub[%s] 丢弃非法行：%s" % (self.key, line[:120]))
                continue
            if "id" in msg and msg["id"] in self._pending:
                slot = self._pending.pop(msg["id"])
                slot["msg"] = msg
                slot["event"].set()
            elif msg.get("method"):
                cb = self.on_notify
                if cb is not None:
                    try:
                        cb(self.key, msg)
                    except Exception:                  # noqa: BLE001
                        pass
        self.alive = False

    def _drain_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        for line in self.proc.stderr:
            self._stderr.append(line.rstrip())

    def _write(self, payload: dict) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict, timeout: float = 3600.0) -> dict:
        with self._lock:
            # 注意：不能用 self.alive 判活——handshake 期间 alive 还是 False，
            # 会把 start() 自己的 initialize/tools/list 挡掉（实测整个 hub 空表）。
            if self.proc is None or self.proc.poll() is not None:
                raise RpcError(-32000, "%s 子进程不在（已退出）" % self.key)
            req_id = self._next_id
            self._next_id += 1
            slot = {"event": threading.Event(), "msg": None}
            self._pending[req_id] = slot
            self.wire["child_req"] = req_id
            try:
                self._write({"jsonrpc": "2.0", "id": req_id,
                             "method": method, "params": params})
                if not slot["event"].wait(timeout):
                    raise RpcError(-32000, "%s 在 %.0fs 内没有回应" % (self.key, timeout))
            finally:
                self._pending.pop(req_id, None)
            msg = slot["msg"] or {}
            if "error" in msg:
                err = msg["error"] or {}
                raise RpcError(err.get("code", -32000),
                               "%s: %s" % (self.key, err.get("message")),
                               err.get("data"))
            return msg.get("result") or {}

    def cancel(self, child_req_id) -> None:
        try:
            self.notify("notifications/cancelled", {"requestId": child_req_id})
        except Exception:                              # noqa: BLE001
            pass


class Hub:
    def __init__(self):
        self.kits: dict[str, KitProcess] = {}
        self._start_lock = threading.Lock()
        self._inflight: dict[object, tuple[str, object]] = {}
        self._inflight_lock = threading.Lock()
        self._error: dict[str, str] = {}
        self._index: dict[str, str] = {}       # 工具名 → 属主 kit

    # ---- 懒启动 ---------------------------------------------------------
    def kit(self, key: str) -> KitProcess:
        with self._start_lock:
            proc = self.kits.get(key)
            if proc is not None and proc.alive and proc.proc and proc.proc.poll() is None:
                return proc
            proc = KitProcess(key, KITS[key])
            proc.on_notify = self._forward_notification
            try:
                proc.start()
                self._error.pop(key, None)
            except Exception as exc:                   # noqa: BLE001
                self._error[key] = "%s: %s" % (type(exc).__name__, exc)
                log("hub 启动 %s 失败：%s" % (key, exc))
                proc.stop()
                raise RpcError(-32000, "kit %s 起不来：%s" % (key, exc))
            self.kits[key] = proc
            return proc

    def kit_or_none(self, key: str) -> KitProcess | None:
        proc = self.kits.get(key)
        if proc is not None and proc.alive and proc.proc and proc.proc.poll() is None:
            return proc
        return None

    # ---- 聚合视图 -------------------------------------------------------
    def ensure_all(self) -> None:
        for key in KITS:
            try:
                self.kit(key)
            except RpcError:
                continue            # 起不来的记在 self._error，status 里如实报

    def all_tools(self) -> list[dict]:
        self.ensure_all()
        tools: list[dict] = []
        seen: set[str] = set()
        for key in KITS:
            proc = self.kit_or_none(key)
            if proc is None:
                continue
            for tool in proc.tools:
                name = tool.get("name") or ""
                if not name or name in seen:
                    continue
                if name == "kit_runtime":
                    # 六个 kit 各有一个同名状态工具；聚合后统一看 nsa_hub_status
                    continue
                seen.add(name)
                self._index[name] = key
                tools.append(tool)
        tools.append({
            "name": "nsa_hub_status",
            "description": ("聚合网关状态：每个 kit 是否存活、工具数、最近错误。"
                            "排查\"某个 kit 掉了\"先看这个。"),
            "inputSchema": {"type": "object", "properties": {},
                            "additionalProperties": False},
        })
        return tools

    def status(self) -> dict:
        rows = []
        for key in KITS:
            proc = self.kit_or_none(key)
            rows.append({
                "kit": key,
                "alive": bool(proc is not None),
                "tools": len(proc.tools) if proc else 0,
                "pid": proc.proc.pid if proc and proc.proc else None,
                "uptime_s": round(time.time() - proc.started_at, 1)
                if proc and proc.started_at else None,
                "error": self._error.get(key),
                "stderr_tail": list(proc._stderr)[-3:] if proc else [],
            })
        alive = [r for r in rows if r["alive"]]
        return {
            "hub": HUB_KEY,
            "version": __version__,
            "kits_total": len(KITS),
            "kits_alive": len(alive),
            "tools_total": sum(r["tools"] for r in alive),
            "kits": rows,
        }

    # ---- 路由 -----------------------------------------------------------
    def _forward_notification(self, key: str, msg: dict) -> None:
        method = msg.get("method") or ""
        if method.startswith("notifications/"):
            params = dict(msg.get("params") or {})
            params.setdefault("kit", key)
            jsonrpc.notify(method, params)

    def call(self, name: str, args: dict, meta: dict | None = None,
             hub_req_id=None) -> dict:
        if name == "nsa_hub_status":
            payload = self.status()
            return {
                "content": [{"type": "text",
                             "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                "structuredContent": payload,
                "isError": False,
            }
        key = self._index.get(name) or owner_of(name)
        if key is None:
            # 客户端可能不调 tools/list 直接调工具：先把索引建起来再试一次
            self.all_tools()
            key = self._index.get(name) or owner_of(name)
        if name == "kit_runtime":
            payload = self.status()
            return {
                "content": [{"type": "text",
                             "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                "structuredContent": payload, "isError": False}
        if key is None:
            raise RpcError(INVALID_PARAMS, "未知工具：%s（hub 认 %s 前缀）"
                           % (name, ", ".join(p + "_" for p in KITS)))
        proc = self.kit(key)
        params: dict = {"name": name, "arguments": args or {}}
        if meta:
            params["_meta"] = meta
        if hub_req_id is not None:
            with self._inflight_lock:
                self._inflight[str(hub_req_id)] = (key, proc)
        try:
            return proc.request("tools/call", params)
        finally:
            if hub_req_id is not None:
                with self._inflight_lock:
                    self._inflight.pop(str(hub_req_id), None)

    def cancel(self, hub_req_id) -> None:
        with self._inflight_lock:
            pair = self._inflight.get(str(hub_req_id))
        if not pair:
            return
        key, proc = pair
        proc.cancel(proc.wire.get("child_req"))
        log("hub 已把取消转给 %s（hub req=%s）" % (key, hub_req_id))


# ---------------------------------------------------------------- MCP 服务
def build_handlers(hub: Hub) -> dict:
    def initialize(params: dict) -> dict:
        requested = params.get("protocolVersion")
        protocol = (requested if requested in jsonrpc.SUPPORTED_PROTOCOLS
                    else jsonrpc.DEFAULT_PROTOCOL)
        log("初始化 %s client=%r protocol=%s"
            % (HUB_KEY, (params.get("clientInfo") or {}).get("name"), protocol))
        return {
            "protocolVersion": protocol,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": HUB_KEY, "version": __version__},
            "instructions": (
                "六合一聚合网关：工具名前缀 sw_/acad_/nx_/gx_/codesys_/autoshop_ 决定路由，"
                "每次调用都转发给对应 kit 子进程，判据（checks）原样返回。"
                "长任务支持 notifications/progress 与 notifications/cancelled。"),
        }

    def tools_list(_params: dict) -> dict:
        return {"tools": hub.all_tools()}

    def tools_call(params: dict) -> dict:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise RpcError(INVALID_PARAMS, "tools/call 需要 name")
        args = params.get("arguments") or {}
        meta = params.get("_meta") or None
        return hub.call(name, args, meta=meta, hub_req_id=jsonrpc.current_request())

    return {
        "initialize": initialize,
        "notifications/initialized": lambda _p: None,
        "tools/list": tools_list,
        "tools/call": tools_call,
        "ping": lambda _p: {},
        "logging/setLevel": lambda _p: {},
    }


def run_server() -> int:
    hub = Hub()
    log("启动 %s v%s（聚合 %d 个 kit）" % (HUB_KEY, __version__, len(KITS)))
    try:
        # tools/call 放线程：否则读循环被阻塞，取消通知进不来（与 kit 服务器同理）
        return jsonrpc.serve(build_handlers(hub),
                             threaded_methods={"tools/call"},
                             on_cancelled=hub.cancel)
    except KeyboardInterrupt:
        return 0
    finally:
        for proc in hub.kits.values():
            proc.stop()
