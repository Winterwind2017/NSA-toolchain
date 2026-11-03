"""工具注册与调用：统一 schema、单飞锁、超时、结果归一化。"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from .contracts import ContractError, validate_against_schema
from .jsonrpc import INVALID_PARAMS, RpcError, log

# 六个 kit 的调用模型差异很大：NX run_journal 冷启动慢、GX 要等窗口出现、
# CODESYS 要走常驻服务。所以超时按 kit 可覆盖。
DEFAULT_TIMEOUT_S = 180.0

# 幂等重放窗口：同一个 request_id 在这么长时间内重试，直接回放上次结果。
REPLAY_TTL_S = 900.0


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], Any]
    timeout_s: float = DEFAULT_TIMEOUT_S
    # 支持下述可选能力：
    idempotent: bool = False        # 接受 request_id，重复调用回放上次结果
    lock_free: bool = False         # 不进单飞锁（用于「现在忙不忙」这类旁路查询）
    must_have_checks: bool = False  # 声明必须有判据；checks 为空即判负
    validator: Callable[[dict], None] | None = None   # 额外的字段级校验


@dataclass
class Kit:
    """一个内核（nxkit / gxkit / …）在 MCP 侧的样子。"""

    key: str                      # 工具名前缀，如 "nx"
    name: str                     # 人类可读名，如 "nxkit"
    version: str = "0.0.0"
    instructions: str = ""
    tools: list[ToolSpec] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # 运行状态（给 kit_runtime 用；不占锁）
    _stats: dict = field(default_factory=dict)
    _replay: dict = field(default_factory=dict)
    _guard: threading.Lock = field(default_factory=threading.Lock)
    _queued: int = 0
    # 跨进程单飞：同一台机器上多个进程驱动同一个 kit 时靠文件锁互斥
    lock_path: str | None = None
    # 超时后仍在跑的 worker（线程式超时的已知代价，显式记下来而不是假装没事）
    _stuck: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._stats.setdefault("calls", 0)
        self._stats.setdefault("failures", 0)
        self._stats.setdefault("replayed", 0)
        self._stats.setdefault("last_tool", None)
        self._stats.setdefault("last_started", None)
        self._stats.setdefault("last_seconds", None)

    # -- 注册 ---------------------------------------------------------------
    def add(self, tool: ToolSpec) -> None:
        self.tools.append(tool)

    def install_test_tools(self) -> None:
        """只有 NSA_MCP_HUB_TEST_TOOLS=1 时才挂：用来真机验证超时/stuck 行为。"""
        if os.environ.get("NSA_MCP_HUB_TEST_TOOLS") != "1":
            return

        def _sleep(args: dict) -> dict:
            """轮询式睡眠：被取消时立刻返回（用来验证取消链路真的通）。"""
            seconds = float(args.get("seconds") or 3)
            deadline = time.time() + seconds
            slept = 0.0
            while time.time() < deadline:
                if is_cancelled():
                    slept = round(time.time() - (deadline - seconds), 2)
                    payload = normalize(self.key, "kit_sleep", ok=False,
                                        reads={"slept": slept, "cancelled": True},
                                        errors=["睡眠被取消"])
                    payload["cancelled"] = True
                    return payload
                time.sleep(0.1)
                slept = round(time.time() - (deadline - seconds), 2)
            return normalize(self.key, "kit_sleep", ok=True,
                             reads={"slept": slept},
                             checks=[{"check": "slept", "got": seconds,
                                      "want": seconds, "ok": True}])

        self.add(ToolSpec("kit_sleep",
                          "测试用：睡 N 秒（超时固定 1 s，用于验证 stuck 守卫）。",
                          {"type": "object",
                           "properties": {"seconds": {"type": "number"}},
                           "additionalProperties": False},
                          _sleep, timeout_s=120.0))

    def runtime_tool(self) -> ToolSpec:
        """每个服务器白送一个「不进锁」的状态查询（列在工具表末尾）。"""
        return ToolSpec(
            "kit_runtime",
            "内核运行状态：是否忙、排队数、调用计数、上次调用耗时与结果（不占单飞锁）。",
            {"type": "object", "properties": {}, "additionalProperties": False},
            self._runtime_payload, timeout_s=10, lock_free=True)

    def tool_map(self) -> dict:
        mapping = {t.name: t for t in self.tools}
        mapping.setdefault("kit_runtime", self.runtime_tool())
        return mapping

    # -- 幂等 ---------------------------------------------------------------
    @staticmethod
    def _replay_key(tool: ToolSpec, args: dict):
        rid = (args or {}).get("request_id")
        if not tool.idempotent or not rid:
            return None
        return (tool.name, str(rid))

    def replay_get(self, tool: ToolSpec, args: dict):
        key = self._replay_key(tool, args)
        if key is None:
            return None
        with self._guard:
            item = self._replay.get(key)
            if item is None:
                return None
            started, payload = item
            if time.time() - started > REPLAY_TTL_S:
                self._replay.pop(key, None)
                return None
            self._stats["replayed"] += 1
        copy = json.loads(json.dumps(payload, ensure_ascii=False))
        copy["replayed"] = True
        copy.setdefault("reads", {})["replayed_from"] = key[1]
        return copy

    def replay_put(self, tool: ToolSpec, args: dict, payload: dict) -> None:
        key = self._replay_key(tool, args)
        if key is None or not isinstance(payload, dict) or not payload.get("ok"):
            return
        with self._guard:
            self._replay[key] = (time.time(),
                                 json.loads(json.dumps(payload, ensure_ascii=False)))

    # -- 状态 ---------------------------------------------------------------
    def _runtime_payload(self, _args: dict) -> dict:
        with self._guard:
            snapshot = dict(self._stats)
            replay_size = len(self._replay)
        return normalize(self.key, "kit_runtime", ok=True,
                         reads={"busy": self.lock.locked(),
                                "queued": self._queued,
                                "tools": len(self.tools),
                                "replay_cache": replay_size,
                                "stuck": self.stuck_tools(),
                                "locked_across_processes": bool(self.lock_path),
                                **snapshot})

    # -- 卡住的调用 -----------------------------------------------------------
    def mark_stuck(self, tool: ToolSpec, seconds: float) -> None:
        with self._guard:
            self._stuck[tool.name] = {"since": time.time(), "seconds": round(seconds, 1)}

    def unmark_stuck(self, tool_name: str) -> None:
        with self._guard:
            self._stuck.pop(tool_name, None)

    def stuck_tools(self) -> list:
        with self._guard:
            return [{"tool": k, "running_seconds": round(time.time() - v["since"], 1)}
                    for k, v in self._stuck.items()]

    def mark_started(self, tool: ToolSpec) -> None:
        with self._guard:
            self._stats["last_tool"] = tool.name
            self._stats["last_started"] = time.strftime("%Y-%m-%d %H:%M:%S")

    def mark_finished(self, tool: ToolSpec, payload: dict, seconds: float) -> None:
        with self._guard:
            self._stats["calls"] += 1
            self._stats["last_seconds"] = round(seconds, 2)
            if not (isinstance(payload, dict) and payload.get("ok")):
                self._stats["failures"] += 1


def _check_ok(check) -> bool:
    """判据条目可能是字典（nxkit/gxkit），也可能是纯文本（acadkit），都要容忍。"""
    if isinstance(check, dict):
        return bool(check.get("ok", True))
    return True


def normalize(kit: str, capability: str, *, ok: bool, reads: dict | None = None,
              checks: list | None = None, errors: list | None = None,
              seconds: float | None = None, **extra) -> dict:
    """六个 kit 共用返回结构；``ok`` 只由 checks + 执行错误决定。"""
    checks = checks or []
    errors = errors or []
    payload = {
        "ok": bool(ok and all(_check_ok(c) for c in checks) and not errors),
        "kit": kit,
        "capability": capability,
        "reads": reads or {},
        "checks": checks,
        "errors": errors,
        "seconds": round(seconds, 2) if seconds is not None else None,
    }
    payload.update(extra)
    return payload


def _com_initialize():
    """在线程里初始化 COM（STA）。

    为什么需要：COM 是**按线程**初始化的。内核把每次调用放到 worker 线程里跑
    （为了能做超时），而 AutoCAD / SolidWorks 的 COM 调用在这个新线程里必须先
    CoInitialize，否则 win32com 会抛 -2147221008「尚未调用 CoInitialize」。
    """
    try:
        import pythoncom                     # pywin32，默认 STA
        pythoncom.CoInitialize()
        return lambda: pythoncom.CoUninitialize()
    except Exception:                        # noqa: BLE001
        pass
    try:
        import ctypes
        ole32 = ctypes.windll.ole32
        hr = ole32.CoInitializeEx(None, 0x2)   # COINIT_APARTMENTTHREADED
        if hr >= 0:
            return lambda: ole32.CoUninitialize()
    except Exception:                        # noqa: BLE001
        pass
    return lambda: None


def apply_checks(payload: dict, checks: list) -> dict:
    """把判据挂到已有载荷上，并重算 ok（只由 checks + errors 决定）。

    给"没有判据体系"的 kit（swkit 代理 / codesys / autoshop）用：判据只能是
    结构性的（后端是否应答、关键读数是否为 0、字段是否出现），但至少让调用方
    看到"凭什么算成功"。
    """
    payload["checks"] = checks
    payload["ok"] = (bool(payload.get("ok"))
                     and all(_check_ok(c) for c in checks)
                     and not (payload.get("errors") or []))
    return payload



# ── P7：取消（notifications/cancelled）与并发安全的取消标志 ─────────────
# 设计：内核只负责"登记 + 让长任务能查到"。能不能真中断，取决于各工具是否轮询
# `is_cancelled()`——脚本类工具（sw/long shell）会 kill 子进程；纯 COM 调用无法
# 中途打断，只能等它返回后把结果标成"已取消"。
_CANCELS: dict = {}
_CANCEL_LOCK = threading.Lock()
_ACTIVE = threading.local()


def register_request(req_id) -> threading.Event:
    """给一个请求 id 建取消标志（同 id 复用）。"""
    key = str(req_id) if req_id is not None else ""
    with _CANCEL_LOCK:
        ev = _CANCELS.get(key)
        if ev is None:
            ev = threading.Event()
            _CANCELS[key] = ev
        return ev


def cancel_request(req_id) -> bool:
    """客户端发来 notifications/cancelled 时调用。"""
    key = str(req_id) if req_id is not None else ""
    with _CANCEL_LOCK:
        ev = _CANCELS.get(key)
    if ev is None:
        return False
    ev.set()
    log("已登记取消：request=%s" % key)
    return True


def forget_request(req_id) -> None:
    key = str(req_id) if req_id is not None else ""
    with _CANCEL_LOCK:
        _CANCELS.pop(key, None)


def current_event():
    """执行线程里的取消标志（没有则为 None）。"""
    return getattr(_ACTIVE, "event", None)


def is_cancelled() -> bool:
    ev = current_event()
    return bool(ev is not None and ev.is_set())


class _FileLock:
    """跨进程互斥（Windows 用 msvcrt，其它平台用 fcntl）。

    为什么需要：进程内的 threading.Lock 只约束**本进程**。如果 DSH 和命令行脚本
    同时驱动同一个 kit，SolidWorks/AutoCAD 的 COM 单实例就会被两个客户端抢。
    """

    def __init__(self, path: str):
        self.path = path
        self.fh = None

    def acquire(self, timeout: float) -> bool:
        import os
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        deadline = time.time() + timeout
        while True:
            try:
                self.fh = open(self.path, "a+b")
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except Exception:                        # noqa: BLE001
                if self.fh is not None:
                    try:
                        self.fh.close()
                    except Exception:                # noqa: BLE001
                        pass
                    self.fh = None
                if time.time() >= deadline:
                    return False
                time.sleep(0.2)

    def release(self) -> None:
        if self.fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        except Exception:                            # noqa: BLE001
            pass
        try:
            self.fh.close()
        except Exception:                            # noqa: BLE001
            pass
        self.fh = None


def run_with_lock(kit: Kit, tool: ToolSpec, args: dict, req_id=None) -> dict:
    """单飞：同一个 kit 的调用串行，避免 COM/NX/UI 会话被并发打乱。

    两层锁：进程内 threading.Lock（线程）+ 可选的文件锁（跨进程）。
    """
    # 测试用：NSA_MCP_HUB_TIMEOUT_SCALE=0.05 可以把所有超时缩短，用来真机验证 stuck 守卫
    try:
        scale = float(os.environ.get("NSA_MCP_HUB_TIMEOUT_SCALE") or "1")
    except ValueError:
        scale = 1.0
    effective_timeout = tool.timeout_s * scale if scale > 0 else tool.timeout_s

    stuck = kit.stuck_tools()
    if stuck:
        return normalize(kit.key, tool.name, ok=False, errors=[
            "上一次调用超时后仍在后台运行（%s，已 %.0f s）；先等它结束，"
            "或重启该 kit 服务器" % (stuck[0]["tool"], stuck[0]["running_seconds"])])

    acquired = kit.lock.acquire(timeout=0.05)
    if not acquired:
        with kit._guard:
            kit._queued += 1
        log("%s 忙，排队中" % kit.name)
        try:
            acquired = kit.lock.acquire(timeout=effective_timeout)
        finally:
            with kit._guard:
                kit._queued -= 1
    if not acquired:
        return normalize(kit.key, tool.name, ok=False,
                         errors=["%s 正忙（等待超过 %.0fs）" % (kit.name, effective_timeout)])

    file_lock = _FileLock(kit.lock_path) if kit.lock_path else None
    if file_lock is not None and not file_lock.acquire(5.0):
        kit.lock.release()
        return normalize(kit.key, tool.name, ok=False, errors=[
            "另一个进程正在使用 %s（文件锁 %s 拿不到，已等 5 s）" % (kit.name, kit.lock_path)])

    box: dict = {}

    event = register_request(req_id)

    def target() -> None:
        started = time.time()
        _ACTIVE.event = event
        release_com = _com_initialize()
        try:
            # 有些 kit 的 runner 会 print()，直接把协议流写脏；执行期一律把
            # stdout 改道到 stderr，保证 stdout 只承载 JSON-RPC。
            with contextlib.redirect_stdout(sys.stderr):
                value = tool.handler(args or {})
            box["value"] = value
        except Exception as exc:                      # noqa: BLE001
            box["error"] = traceback.format_exc(limit=8)
            box["exc"] = "%s: %s" % (type(exc).__name__, exc)
        finally:
            box["seconds"] = time.time() - started
            kit.unmark_stuck(tool.name)
            try:
                release_com()
            except Exception:                         # noqa: BLE001
                pass

    worker = threading.Thread(target=target, name="%s:%s" % (kit.key, tool.name),
                              daemon=True)
    worker.start()
    worker.join(effective_timeout)
    try:
        if worker.is_alive():
            kit.mark_stuck(tool, effective_timeout)
            return normalize(kit.key, tool.name, ok=False,
                             errors=["调用超时（>%.0fs），该工具仍在后台运行；"
                                     "后续调用会被挡住直到它结束" % effective_timeout],
                             stuck=True)
        if "error" in box:
            log("工具 %s 抛异常：\n%s" % (tool.name, box["error"]))
            return normalize(kit.key, tool.name, ok=False,
                             errors=[box["exc"]], traceback=box["error"].splitlines()[-6:])
        value = box.get("value")
        if isinstance(value, dict):
            value.setdefault("kit", kit.key)
            value.setdefault("capability", tool.name)
            if "seconds" not in value:
                value["seconds"] = round(box.get("seconds", 0.0), 2)
            if "ok" not in value:
                value["ok"] = not value.get("errors")
            if "checks" not in value:
                value["checks"] = []
            if "reads" not in value:
                value["reads"] = {}
            if "errors" not in value:
                value["errors"] = []
            return value
        return normalize(kit.key, tool.name, ok=True,
                         reads={"value": value}, seconds=box.get("seconds"))
    finally:
        if file_lock is not None:
            file_lock.release()
        kit.lock.release()


def call_tool(kit: Kit, name: str, args: dict, req_id=None) -> dict:
    tool = kit.tool_map().get(name)
    if tool is None:
        raise RpcError(INVALID_PARAMS, "未知工具：%s" % name)
    if not isinstance(args, dict):
        raise RpcError(INVALID_PARAMS, "arguments 必须是对象")

    # ① 字段级校验：把明显的调用错误挡在执行之前，错误信息点名参数
    try:
        validate_against_schema(args, tool.input_schema)
        if tool.validator is not None:
            tool.validator(args)
    except ContractError as exc:
        payload = normalize(kit.key, name, ok=False, errors=[str(exc)])
        kit.mark_finished(tool, payload, 0.0)
        return payload

    # ② 幂等重放：同一个 request_id 重复调用不发第二次副作用
    replayed = kit.replay_get(tool, args)
    if replayed is not None:
        return replayed

    # ③ 旁路状态查询不进单飞锁
    if tool.lock_free:
        payload = tool.handler(args or {})
        kit.mark_finished(tool, payload, 0.0)
        return payload

    kit.mark_started(tool)
    payload = run_with_lock(kit, tool, args, req_id=req_id)

    # ④ 声明「必须有判据」的工具，checks 为空即判负
    if tool.must_have_checks and isinstance(payload, dict) and not payload.get("checks"):
        payload["errors"] = list(payload.get("errors") or []) + \
            ["该工具声明必须有判据，但返回里 checks 为空"]
        payload["ok"] = False

    kit.replay_put(tool, args, payload)
    kit.mark_finished(tool, payload, float(payload.get("seconds") or 0.0))
    return payload


def tool_listing(kit: Kit) -> list:
    rows = [{"name": t.name, "description": t.description,
             "inputSchema": t.input_schema} for t in kit.tools]
    runtime = kit.runtime_tool()
    rows.append({"name": runtime.name, "description": runtime.description,
                 "inputSchema": runtime.input_schema})
    return rows


def text_result(payload: dict) -> dict:
    return {
        "content": [{"type": "text",
                     "text": json.dumps(payload, ensure_ascii=False, indent=1)}],
        "structuredContent": payload,
        "isError": not payload.get("ok", False),
    }
