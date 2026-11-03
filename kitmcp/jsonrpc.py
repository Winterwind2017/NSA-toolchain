"""stdio JSON-RPC 2.0 传输：一行一条消息，日志只走 stderr。"""

from __future__ import annotations

import json
import queue
import sys
import threading
import traceback

JSONRPC_VERSION = "2.0"

# MCP 协议版本：优先回显客户端要求的版本，否则用我们支持的最新版。
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = SUPPORTED_PROTOCOLS[0]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def log(message: str) -> None:
    """诊断输出只写 stderr，绝污染 stdout 的协议流。"""
    sys.stderr.write("[kitmcp] %s\n" % message)
    sys.stderr.flush()


class RpcError(Exception):
    def __init__(self, code: int, message: str, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


# 协议流必须绑在**启动时的真实 stdout** 上。
# 原因：执行工具时 worker 线程里用 contextlib.redirect_stdout 把 sys.stdout 临时改到
# stderr（防止 runner 的 print 污染协议流），而那个改动是**进程全局**的——如果某次调用
# 超时、worker 还在跑，后续响应就会跟着被写进 stderr，客户端永远收不到回复。
_STDOUT = sys.stdout


_WRITE_LOCK = threading.Lock()
_LOCAL = threading.local()


def current_request():
    """当前正在处理的 JSON-RPC 请求 id（供取消/进度用）。"""
    return getattr(_LOCAL, "request_id", None)


def _write(payload: dict, stream=None) -> None:
    stream = stream or _STDOUT
    text = json.dumps(payload, ensure_ascii=False)
    with _WRITE_LOCK:                 # 进度通知来自另一个线程，必须串行化
        stream.write(text + "\n")
        stream.flush()


def notify(method: str, params: dict, stream=None) -> None:
    """服务端主动发通知（notifications/progress 等）。"""
    _write({"jsonrpc": JSONRPC_VERSION, "method": method,
            "params": params or {}}, stream)


def result(msg_id, value, stream=None) -> None:
    _write({"jsonrpc": JSONRPC_VERSION, "id": msg_id, "result": value}, stream)


def error(msg_id, code: int, message: str, data=None, stream=None) -> None:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    _write({"jsonrpc": JSONRPC_VERSION, "id": msg_id, "error": err}, stream)


def read_messages(stream=None):
    """逐行读 JSON-RPC 消息；空行与非法行被忽略并记日志。"""
    stream = stream or sys.stdin
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            log("丢弃非法 JSON 行：%s" % exc)
            yield None


def serve(handlers: dict, on_exit=None, instream=None, outstream=None,
          threaded_methods=(), on_cancelled=None) -> int:
    """主循环。

    ``handlers`` 映射方法名 → 可调用对象 ``fn(params) -> result``；
    方法名以 ``notification/`` 开头的消息不写响应。

    ``threaded_methods`` 里的方法在**独立线程**执行，读循环继续跑——这是取消能生效的
    前提：否则 `tools/call` 一阻塞，`notifications/cancelled` 根本读不进来，
    客户端永远等不到"已取消"。
    """
    threaded = set(threaded_methods or ())
    inbox: "queue.Queue" = queue.Queue()

    def _reader() -> None:
        for item in read_messages(instream):
            if (isinstance(item, dict) and on_cancelled is not None
                    and item.get("method") == "notifications/cancelled"):
                try:
                    on_cancelled((item.get("params") or {}).get("requestId"))
                except Exception:                   # noqa: BLE001
                    pass
                continue
            inbox.put(item)
        inbox.put(None)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    threads: list = []

    def _run_threaded(method: str, params: dict, msg_id) -> None:
        _LOCAL.request_id = msg_id
        log("_run_threaded 开始 %s id=%r" % (method, msg_id))
        try:
            value = handlers[method](params)
        except RpcError as exc:
            error(msg_id, exc.code, exc.message, exc.data, stream=outstream)
            return
        except Exception as exc:                      # noqa: BLE001
            log("处理 %s 时异常：\n%s" % (method, traceback.format_exc(limit=6)))
            error(msg_id, INTERNAL_ERROR, "%s: %s" % (type(exc).__name__, exc),
                  stream=outstream)
            return
        log("_run_threaded 写回复 id=%r" % (msg_id,))
        result(msg_id, value, outstream)

    while True:
        msg = inbox.get()
        if msg is None:
            break
        if msg is None:
            error(None, PARSE_ERROR, "无法解析的 JSON", stream=outstream)
            continue
        if not isinstance(msg, dict):
            error(None, INVALID_REQUEST, "消息必须是对象", stream=outstream)
            continue

        method = msg.get("method")
        msg_id = msg.get("id")
        is_notification = "id" not in msg

        if not isinstance(method, str):
            if not is_notification:
                error(msg_id, INVALID_REQUEST, "缺少 method", stream=outstream)
            continue

        if method == "exit":
            if on_exit:
                on_exit()
            return 0

        handler = handlers.get(method)
        if handler is None:
            if method.startswith("notifications/"):
                continue          # 通知不回应，也不必报错
            if not is_notification:
                error(msg_id, METHOD_NOT_FOUND, "未知方法：%s" % method, stream=outstream)
            continue

        params = msg.get("params") or {}
        if method in threaded and not is_notification:
            t = threading.Thread(target=_run_threaded,
                                 args=(method, params, msg_id), daemon=True)
            t.start()
            threads.append(t)
            continue
        _LOCAL.request_id = msg_id
        try:
            value = handler(params)
        except RpcError as exc:
            if not is_notification:
                error(msg_id, exc.code, exc.message, exc.data, stream=outstream)
            continue
        except Exception as exc:                      # noqa: BLE001
            log("处理 %s 时异常：\n%s" % (method, traceback.format_exc(limit=6)))
            if not is_notification:
                error(msg_id, INTERNAL_ERROR, "%s: %s" % (type(exc).__name__, exc), stream=outstream)
            continue

        if is_notification:
            continue
        # 通知型方法（如 notifications/initialized）即使带 id 也不回结果体
        if method.startswith("notifications/"):
            continue
        log("_run_threaded 写回复 id=%r" % (msg_id,))
        result(msg_id, value, outstream)

    # 输入关闭：等还在跑的工具线程收尾（避免半截响应）
    for t in threads:
        t.join(timeout=120.0)
    return 0
