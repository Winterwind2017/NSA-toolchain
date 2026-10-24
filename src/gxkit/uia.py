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

PANE_CLASS = "XTPDockingPaneTabbedContainer"
OUTPUT_COLUMNS = ("no", "result", "data", "category", "content", "code")


def _pane_hwnd(pid: int, title: str) -> int:
    """找标题含 title 的停靠面板（XTPDockingPaneTabbedContainer）。"""
    import win32gui

    from .win import windows

    frame = next((w["hwnd"] for w in windows(pid) if w["class"] == "GXW3FrameWnd"), 0)
    if not frame:
        return 0
    hits = []

    def cb(hwnd, _):
        if win32gui.GetClassName(hwnd) == PANE_CLASS and title in win32gui.GetWindowText(hwnd):
            hits.append(hwnd)
        return True

    win32gui.EnumChildWindows(frame, cb, None)
    return hits[0] if hits else 0


def _grid_of(hwnd: int):
    obj, UIA = automation()
    cond = obj.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50007)
    return obj, UIA, element(hwnd).FindFirst(4, cond)


def _header_names(obj, UIA, grid) -> list[str]:
    try:
        cond = obj.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50034)
        head = grid.FindFirst(4, cond)
        if not head:
            return []
        items = head.FindAll(4, obj.CreatePropertyCondition(
            UIA.UIA_ControlTypePropertyId, 50035))
        return [(items.GetElement(i).CurrentName or "").strip()
                for i in range(items.Length)]
    except Exception:
        return []


def output_rows(pid: int, title: str = "输出") -> dict:
    """读「输出」面板的表格（编译器/检查器的消息）。

    返回 {"pane": hwnd, "header": [...], "rows": [{no,result,data,category,content,code}]}
    """
    hwnd = _pane_hwnd(pid, title)
    if not hwnd:
        return {"pane": 0, "header": [], "rows": []}
    obj, UIA, grid = _grid_of(hwnd)
    if not grid:
        return {"pane": hwnd, "header": [], "rows": []}
    header = _header_names(obj, UIA, grid)
    cond = obj.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50020)
    items = grid.FindAll(4, cond)
    names = [(items.GetElement(i).CurrentName or "").strip()
             for i in range(items.Length)]
    ncol = len(header) or len(OUTPUT_COLUMNS)
    rows = []
    for i in range(0, len(names), ncol):
        chunk = names[i:i + ncol]
        if len(chunk) < ncol:
            break
        row = dict(zip(OUTPUT_COLUMNS[:ncol], chunk))
        rows.append(row)
    return {"pane": hwnd, "header": header, "rows": rows}


def output_text(pid: int, title: str = "输出") -> list[str]:
    """把「输出」面板每行拼成 "分类｜内容｜错误代码" 的字符串。"""
    out = []
    for r in output_rows(pid, title)["rows"]:
        bits = [r.get("category", ""), r.get("content", ""), r.get("code", "")]
        line = "｜".join(b for b in bits if b)
        if line:
            out.append(line)
    return out

def nav_pane_hwnd(pid: int) -> int:
    return _pane_hwnd(pid, "导航")


def nav_tree_rows(pid: int) -> list[dict]:
    """导航树里的行：[(name, element, (x, y))]；名字形如 `PrgOne タイトル…`。"""
    hwnd = nav_pane_hwnd(pid)
    if not hwnd:
        return []
    obj, UIA = automation()
    el = element(hwnd)
    cond = obj.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50025)
    try:
        items = el.FindAll(4, cond)
    except Exception:
        return []
    rows = []
    for i in range(items.Length):
        it = items.GetElement(i)
        try:
            nm = (it.CurrentName or "").strip()
            r = it.CurrentBoundingRectangle
            rows.append({"name": nm, "element": it,
                         "pt": ((r.left + r.right) // 2, (r.top + r.bottom) // 2),
                         "rect": (r.left, r.top, r.right, r.bottom)})
        except Exception:
            continue
    return rows


def open_program(pid: int, name: str, offsets: tuple[int, ...] = (0,)) -> dict:
    """双击 `name` 下面那一行「程序本体」，把该程序的**程序本体**页切到前台。

    做法：按行名定位程序行 → 取它后面最近的一行「程序本体」→ 用那一行自己的
    矩形中心双击（不靠"父行 + N 像素"猜，父行被单击可能折叠子树）。
    判定：窗口标题里既有程序名，又有 `[ST]`（「局部标签设置」页也会带程序名）。
    """
    from .win import activate, click, windows

    frame = next((w["hwnd"] for w in windows(pid) if w["class"] == "GXW3FrameWnd"), 0)
    if not frame:
        return {"opened": False, "title": "", "offset": None}

    for attempt in range(2):
        rows = nav_tree_rows(pid)
        idx = next((i for i, r in enumerate(rows)
                    if r["name"] == name or r["name"].startswith(name + " ")), None)
        if idx is None:
            return {"opened": False, "title": "", "offset": None}
        body = next((r for r in rows[idx + 1:idx + 4] if r["name"] == "程序本体"), None)
        if body is None:
            # 没展开：双击父行展开后再来一轮
            activate(frame)
            click(rows[idx]["pt"][0], rows[idx]["pt"][1], settle=0.10)
            click(rows[idx]["pt"][0], rows[idx]["pt"][1], settle=0.8)
            continue
        activate(frame)
        x, y = body["pt"]
        # UIA 的行矩形和视觉位置有 ~13px 偏差（probe131 在 +13 处才点开），
        # 所以在 ±20px 内扫几个点，用标题里的 `[ST]` 当成功判据。
        for dy in (0, 6, 12, 18, -6):
            click(x, y + dy, settle=0.10)
            click(x, y + dy, settle=1.0)
            title = _window_title(frame)
            if name in title and "[ST]" in title:
                return {"opened": True, "title": title, "offset": dy}
    return {"opened": False, "title": _window_title(frame), "offset": None}


def _window_title(hwnd: int) -> str:
    import win32gui
    try:
        return win32gui.GetWindowText(hwnd)
    except Exception:
        return ""

def mdi_child(pid: int, needle: str) -> int:
    """找标题含 needle 的 MDI 子窗口（文档页），例如 `校验结果 [工程校验]`。"""
    from .win import windows

    for w in windows(pid):
        if needle in (w.get("title") or ""):
            return w["hwnd"]
    return 0


def grid_rows(hwnd: int, ncol: int = 0) -> dict:
    """读窗口里的 DataGrid：按文档顺序收集 DataItem 的 Name，每 ncol 个切一行。"""
    obj, UIA, grid = _grid_of(hwnd)
    if not grid:
        return {"header": [], "rows": []}
    header = _header_names(obj, UIA, grid)
    n = ncol or len(header) or 6
    cond = obj.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50020)
    try:
        items = grid.FindAll(4, cond)
    except Exception:
        return {"header": header, "rows": []}
    names = [(items.GetElement(i).CurrentName or "").strip()
             for i in range(items.Length)]
    rows = []
    for i in range(0, len(names), n):
        chunk = names[i:i + n]
        if len(chunk) < n:
            break
        rows.append(chunk)
    return {"header": header, "rows": rows}

