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


def clean_quit(app: Any, save: bool = False, wait_s: float = 15.0) -> dict:
    """干净退出：先处理文档，再 Quit，最后等进程真的消失。

    三个坑（本仓库实测）：

    1. `app.Documents` 在晚绑定下**不支持直接枚举**（`TypeError: This object does
       not support enumeration`）→ 必须按索引 `Documents.Item(i)` 取。
    2. 文档未保存时 `Quit()` 会弹模态框把调用卡住 → `save=False` 要先把
       `doc.Saved = True`（**丢弃**修改）再退出。
    3. `Quit()` 是异步的：调用返回后进程还会活几秒 → 必须轮询等它消失，
       否则下一个用例会看到"幽灵实例"。
    """
    out: dict = {"ok": False, "documents": [], "error": None,
                 "process_exited": None, "waited_s": 0.0}
    try:
        count = int(app.Documents.Count)
        for i in range(count):
            doc = app.Documents.Item(i)
            saved = bool(getattr(doc, "Saved", True))
            out["documents"].append({"name": getattr(doc, "Name", "?"),
                                     "saved": saved})
            if save:
                doc.Save()
            elif not saved:
                try:
                    doc.Saved = True     # 丢弃修改，避免 Quit 弹模态
                except Exception:        # noqa: BLE001
                    pass
        app.Quit()
        out["ok"] = True
    except Exception as exc:            # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
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
