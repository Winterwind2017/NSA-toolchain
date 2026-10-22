"""UIA 薄封装：只做"按名字找控件/点按钮/读文本"，不承载业务。

GX Works3 的菜单是 XTPPopupBar（MFC/Toolkit Pro）：
  - 子菜单项**不能**直接 Invoke（COMError -2146233083）
  - 必须先 Alt+字母 把菜单弹出来，再对 popup 窗口里的 MenuItem Invoke
"""

from __future__ import annotations

import time

_uia = None


def automation():
    global _uia
    if _uia is None:
        import comtypes.client

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA

        _uia = (comtypes.client.CreateObject(
            "{FF48DBA4-60EF-4201-AA87-54103EEF594E}", interface=UIA.IUIAutomation), UIA)
    return _uia


def element(hwnd: int):
    uia, _ = automation()
    return uia.ElementFromHandle(hwnd)


def _find(hwnd: int, control_type: int):
    _, UIA = automation()
    el = element(hwnd)
    return el.FindAll(
        _UIA_TreeScope_Descendants(), _prop_condition(control_type))


def _UIA_TreeScope_Descendants():
    return 4


def _prop_condition(control_type: int):
    uia, UIA = automation()
    return uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, control_type)


def buttons(hwnd: int) -> list[tuple[str, int, int]]:
    out = []
    try:
        items = _find(hwnd, 50000)
        for i in range(items.Length):
            it = items.GetElement(i)
            r = it.CurrentBoundingRectangle
            out.append(((it.CurrentName or "").strip(),
                        (r.left + r.right) // 2, (r.top + r.bottom) // 2))
    except Exception:
        return []
    return out


def button(hwnd: int, prefixes: tuple[str, ...]):
    for name, x, y in buttons(hwnd):
        if any(name.startswith(p) for p in prefixes):
            return name, x, y
    return None


def menu_items(pid: int) -> list[dict]:
    """当前所有弹出菜单里的项（含所属 popup 标题）。"""
    from .win import windows

    out = []
    for w in windows(pid):
        if w["class"] != "XTPPopupBar":
            continue
        names = []
        try:
            items = _find(w["hwnd"], 50011)
            for i in range(items.Length):
                nm = (items.GetElement(i).CurrentName or "").strip()
                if nm and nm not in names:
                    names.append(nm)
        except Exception:
            continue
        out.append({"title": w["title"], "items": names})
    return out


def invoke_menu_item(prefix: str) -> bool:
    """在已弹出的菜单里按前缀点一项。"""
    from .win import windows

    _, UIA = automation()
    for w in windows(_current_pid()):
        if w["class"] != "XTPPopupBar":
            continue
        try:
            items = _find(w["hwnd"], 50011)
            for i in range(items.Length):
                it = items.GetElement(i)
                if (it.CurrentName or "").strip().startswith(prefix):
                    it.GetCurrentPattern(UIA.UIA_InvokePatternId).QueryInterface(
                        UIA.IUIAutomationInvokePattern).Invoke()
                    return True
        except Exception:
            continue
    return False


_PID = None


def bind_pid(pid: int) -> None:
    global _PID
    _PID = pid


def _current_pid() -> int:
    return _PID or 0


def texts(hwnd: int) -> list[str]:
    import win32gui

    out = []

    def cb(h, _):
        t = win32gui.GetWindowText(h).strip()
        if t:
            out.append(t[:120])

    win32gui.EnumChildWindows(hwnd, cb, None)
    return out


def settle(seconds: float = 0.6) -> None:
    time.sleep(seconds)


def find_names(hwnd: int, needle: str, max_nodes: int = 6000) -> list[str]:
    """在窗口的 UIA 树里找名字含 
eedle 的节点。

    用途：结构体 / 功能块 这类对象在 .gx3 里搜不到明文（二进制/压缩），
    但**导航树里看得见**（实测：导入结构体后出现 StructGen タイトル Struct1）。
    """
    from comtypes.client import CreateObject
    import comtypes.gen.UIAutomationClient as UIA  # noqa: F401

    auto = CreateObject(UIA.CUIAutomation)
    root = auto.ElementFromHandle(hwnd)
    walker = auto.RawViewWalker
    stack = [root]
    found: list[str] = []
    walked = 0
    while stack and walked < max_nodes:
        el = stack.pop()
        walked += 1
        try:
            name = el.CurrentName
        except Exception:
            continue
        if name and needle in name:
            found.append(name)
        try:
            child = walker.GetFirstChildElement(el)
            while child:
                stack.append(child)
                child = walker.GetNextSiblingElement(child)
        except Exception:
            pass
    return found
