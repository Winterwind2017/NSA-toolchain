"""COM 附加层：**只附加，不启动**。

关键教训（本仓库实测，2026-10-21）：

    from win32com.client import dynamic
    app = dynamic.Dispatch("AutoCAD.Application")   # ← 未运行时会**启动**一个隐藏实例

一次 `status` 探测就凭空拉起了一个 acad.exe（Visible=False、自带 Drawing1.dwg），
必须再 `Quit()` 收掉。所以：

* 只读命令 → `attach()`（走 `GetActiveObject`，失败就报"未运行"）
* 需要启动 → 显式调用 `launch()`，并且调用方要负责 `clean_quit()`
"""

from __future__ import annotations

import subprocess
import time
from typing import Any, Optional


class AcadNotRunning(RuntimeError):
    """AutoCAD 未运行（只读命令的**正常**结果，不是错误）。"""


class AcadComError(RuntimeError):
    """COM 调用失败。"""


def attach() -> Any:
    """附加到**已在运行**的 AutoCAD；未运行则抛 `AcadNotRunning`。"""
    import win32com.client as win32

    try:
        return win32.GetActiveObject("AutoCAD.Application")
    except Exception as exc:                        # noqa: BLE001
        raise AcadNotRunning(str(exc)) from exc


def attach_or_none() -> Optional[Any]:
    try:
        return attach()
    except AcadNotRunning:
        return None


def active_documents(app: Any) -> int:
    try:
        return int(app.Documents.Count)
    except Exception:                               # noqa: BLE001
        return -1


def get_var(app: Any, name: str) -> Optional[str]:
    """读系统变量。

    系统变量是**文档级**的：没有打开的文档就读不到。
    这里不为了读数去新建文档（那会产生副作用），直接返回 None。
    """
    try:
        doc = app.ActiveDocument
        return str(doc.GetVariable(name))
    except Exception:                               # noqa: BLE001
        return None


def set_var(app: Any, name: str, value: Any) -> bool:
    try:
        app.ActiveDocument.SetVariable(name, value)
        return True
    except Exception:                               # noqa: BLE001
        return False


def refresh(app: Any) -> Any:
    """重新附加一次；**假对象原样返回**。

    离线测试用 FakeApp（没有 `_oleobj_`）驱动 `clean_quit`。如果这里无条件
    `GetActiveObject`，在装了 pywin32 的机器上会连到**用户真正开着的 AutoCAD**
    并把它 Quit 掉 —— 测试绝不能有这个副作用。
    """
    if not hasattr(app, "_oleobj_"):
        return app
    return attach_or_none() or app


def clean_quit(app: Any, save: bool = False, wait_s: float = 15.0) -> dict:
    """干净退出：先处理文档，再 Quit，最后等进程真的消失。

    三个坑（本仓库实测）：

    1. `app.Documents` 在晚绑定下**不支持直接枚举**（`TypeError: This object does
       not support enumeration`）→ 必须按索引 `Documents.Item(i)` 取。
    2. 文档未保存时 `Quit()` 会弹模态框把调用卡住 → `save=False` 要先把
       `doc.Saved = True`（**丢弃**修改）再退出。
    3. `Quit()` 是异步的：调用返回后进程还会活几秒 → 必须轮询等它消失，
       否则下一个用例会看到"幽灵实例"。
    4. **刚关完文档时 `app.Documents` 可能已经失效**（`AttributeError:
       AutoCAD.Application.Documents`）→ 每次退出前重新 `GetActiveObject`，
       遇到代理失效就再取一次（真机实测：不重取会出现"以为退出了其实没退"）。
    """
    out: dict = {"ok": False, "documents": [], "error": None,
                 "process_exited": None, "waited_s": 0.0}
    last: Optional[BaseException] = None
    for attempt in range(4):
        fresh = refresh(app)
        try:
            count = int(retry(lambda: fresh.Documents.Count,
                              label="Documents.Count"))
            doc_rows = []
            for i in range(count):
                doc = retry(lambda i=i: fresh.Documents.Item(i), label="Documents.Item")
                saved = bool(getattr(doc, "Saved", True))
                doc_rows.append({"name": getattr(doc, "Name", "?"),
                                 "saved": saved})
                if save:
                    retry(lambda d=doc: d.Save(), label="Save")
                elif not saved:
                    try:
                        doc.Saved = True     # 丢弃修改，避免 Quit 弹模态
                    except Exception:        # noqa: BLE001
                        pass
            out["documents"] = doc_rows
            fresh.Quit()
            out["ok"] = True
            break
        except Exception as exc:        # noqa: BLE001
            last = exc
            if isinstance(exc, AttributeError) or is_busy_error(exc):
                time.sleep(0.8)
                app = refresh(app)
                continue
            out["error"] = "%s: %s" % (type(exc).__name__, exc)
            return out

    if not out["ok"]:
        out["error"] = out["error"] or "%s: %s" % (type(last).__name__, last)
        return out

    # 等进程消失（Quit 异步）
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if _proc_count() <= 0:
            out["process_exited"] = True
            out["waited_s"] = round(wait_s - (deadline - time.time()), 1)
            return out
        time.sleep(0.5)
    out["process_exited"] = _proc_count() <= 0
    out["waited_s"] = wait_s
    return out


def _proc_count(name: str = "acad") -> int:
    """数 acad.exe（tasklist，不引入 psutil 依赖）。"""
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s.exe" % name],
                           capture_output=True, text=True, timeout=10,
                           encoding="utf-8", errors="replace")
        return sum(1 for line in r.stdout.splitlines()
                   if line.lower().startswith(name.lower() + ".exe"))
    except Exception:                   # noqa: BLE001
        return -1


# ── COM 忙/拒收重试 ─────────────────────────────────────────────────
# AutoCAD 在关闭/保存文档后会短暂"拒收呼叫"（RPC_E_CALL_REJECTED）。
# 这不是能力失败，而是 COM 的忙等待约定，必须重试；把它当失败会得到
# 一堆假阴性（本仓库实测：关文档后立刻 Documents.Add() 必挂）。
_RETRY_HRESULTS = (-2147418111,    # 0x80010001 RPC_E_CALL_REJECTED
                   -2147417846)    # 0x8001010A RPC_E_SERVERCALL_RETRYLATER


def is_busy_error(exc: BaseException) -> bool:
    code = getattr(exc, "hresult", None)
    if code is None:
        try:
            code = exc.args[0]      # pywintypes.com_error: (hresult, text, ...)
        except (IndexError, TypeError):
            code = None
    if code in _RETRY_HRESULTS:
        return True
    text = str(exc).lower()
    return ("rejected by callee" in text or "拒收" in text
            or "拒绝接收" in text or "server call" in text)


def retry(fn, attempts: int = 25, delay: float = 0.4, label: str = ""):
    """跑一个 COM 调用，遇到"忙/拒收"就等一会儿重试；其它异常原样抛出。"""
    last: Optional[BaseException] = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:        # noqa: BLE001
            if not is_busy_error(exc):
                raise
            last = exc
            time.sleep(delay * (1.0 + i * 0.1))
    raise AcadComError("COM 一直忙（%s，重试 %d 次）：%s"
                       % (label or "call", attempts, last))

