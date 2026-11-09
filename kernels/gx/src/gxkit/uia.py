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

    # 冷启动时先"热身"：打开默认程序 ProgPou（它一定在树里），
    # 让 MDI 标签栏/导航栏布局稳定下来，再去找目标程序。
    if name != "ProgPou":
        for _ in range(2):
            rows_w = nav_tree_rows(pid)
            if not any(r["name"] == "ProgPou" for r in rows_w):
                break
            idx_w = next(i for i, r in enumerate(rows_w) if r["name"] == "ProgPou")
            body_w = next((r for r in rows_w[idx_w + 1:idx_w + 4]
                           if r["name"] == "程序本体"), None)
            if not body_w:
                break
            activate(frame)
            for dy in (0, 6, 12, -6):
                click(body_w["pt"][0], body_w["pt"][1] + dy, settle=0.10)
                click(body_w["pt"][0], body_w["pt"][1] + dy, settle=0.8)
                if "ProgPou" in _window_title(frame) and "[ST]" in _window_title(frame):
                    break
            break

    # 关键：左侧停靠面板可能停在「连接目标」页，必须先切到「导航」标签，
    # 否则读到的是隐藏树的行、点在可见的别的页面上（冷启动必失败）。
    activate_pane_tab(pid, "导航")

    # 再把主窗最大化：导航面板变高后所有行都可见（自绘树不响应合成滚轮）
    try:
        import ctypes as _ct
        _ct.windll.user32.ShowWindow(frame, 3)   # SW_MAXIMIZE
        import time as _t2
        _t2.sleep(1.0)
    except Exception:
        pass

    # 三轮：每轮「点顶层行拿焦点 → 滚到可见 → 行中心上下扫点双击」。
    # 单轮偶然失手（首启后布局不同 / 焦点没拿到）就再来一轮。
    import time as _t

    for _round in range(3):
        if _round:
            _t.sleep(2.0)          # 轮次之间给界面一点时间（时序敏感）
        # 冷启动时导航树是懒加载的：先轮询等目标行出现（最多 ~25 秒）
        rows = sys_rows = []
        for _ in range(25):
            sys_rows = nav_tree_rows(pid)
            rows = sys_rows
            if any(r["name"] == name or r["name"].startswith(name + " ")
                   for r in rows):
                break
            top0 = next((r for r in rows if r["name"] == "工程"), None)
            activate(frame)
            if top0:
                click(top0["pt"][0], top0["pt"][1], settle=0.3)
            _t.sleep(0.8)
        top = next((r for r in rows if r["name"] == "工程"), None)
        activate(frame)
        if top:
            click(top["pt"][0], top["pt"][1], settle=0.4)
        scroll_rows_into_view(pid, name)
        rows = nav_tree_rows(pid)
        idx = next((i for i, r in enumerate(rows)
                    if r["name"] == name or r["name"].startswith(name + " ")), None)
        if idx is None:
            continue
        body = next((r for r in rows[idx + 1:idx + 4] if r["name"] == "程序本体"), None)
        if body is None:
            # 没展开：双击父行展开，下一轮再来
            click(rows[idx]["pt"][0], rows[idx]["pt"][1], settle=0.10)
            click(rows[idx]["pt"][0], rows[idx]["pt"][1], settle=0.8)
            continue
        x, y = body["pt"]
        import os as _os
        if _os.environ.get("GXKIT_DEBUG_OPEN"):
            print("[open] round=%d rows=%d body=%s pane=%s"
                  % (_round, len(rows), body["rect"], _pane_rect(nav_pane_hwnd(pid))),
                  flush=True)
        # UIA 行矩形与视觉位置有 ~13px 偏差，±20px 内扫点，以标题里的 `[ST]` 为判据
        for dy in (0, 6, 12, 18, -6):
            click(x, y + dy, settle=0.10)
            click(x, y + dy, settle=1.0)
            title = _window_title(frame)
            if _os.environ.get("GXKIT_DEBUG_OPEN"):
                print("[open]   dy=%+d title=%r" % (dy, title[-50:]), flush=True)
            if name in title and "[ST]" in title:
                return {"opened": True, "title": title, "offset": dy}
    try:
        import pathlib as _pl
        from PIL import ImageGrab
        _p = _pl.Path.home() / "open_program_fail.png"
        ImageGrab.grab().save(_p)
        print("[open] 失败截图:", _p, flush=True)
    except Exception:
        pass
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

def _pane_rect(hwnd: int):
    import win32gui
    return win32gui.GetWindowRect(hwnd)


def _visible_in_pane(pane: int, rect) -> bool:
    """只看中心点是否在面板内（留 2px 边）。"""
    p = _pane_rect(pane)
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    return p[0] + 2 <= cx <= p[2] - 2 and p[1] + 2 <= cy <= p[3] - 2


def scroll_rows_into_view(pid: int, name: str, below: str = "程序本体",
                          max_steps: int = 12) -> bool:
    """按方向滚动导航树，把 `name` 下面那行 `below` 的中心滚进面板。

    方向很重要：行在面板**上方**要往上滚（+120），在下方才往下滚（-120）。
    """
    import ctypes
    import time as _t

    pane = nav_pane_hwnd(pid)
    if not pane:
        return False
    u32 = ctypes.windll.user32
    p = _pane_rect(pane)
    cx_pane, cy_pane = (p[0] + p[2]) // 2, (p[1] + p[3]) // 2
    for _ in range(max_steps):
        rows = nav_tree_rows(pid)
        idx = next((i for i, r in enumerate(rows)
                    if r["name"] == name or r["name"].startswith(name + " ")), None)
        if idx is None:
            return False
        body = next((r for r in rows[idx + 1:idx + 4] if r["name"] == below), None)
        target = body or rows[idx]
        if _visible_in_pane(pane, target["rect"]):
            return True
        cy_row = (target["rect"][1] + target["rect"][3]) // 2
        delta = -120 if cy_row > p[3] else 120
        u32.SetCursorPos(int(cx_pane), int(cy_pane))
        u32.mouse_event(0x0800, 0, 0, delta, 0)
        _t.sleep(0.45)
    return False

def activate_pane_tab(pid: int, tab_name: str) -> bool:
    """点停靠面板的标签页（`导航` / `输出` / `进度` / `转换结果` …）。"""
    from .win import click, windows

    frame = next((w["hwnd"] for w in windows(pid) if w["class"] == "GXW3FrameWnd"), 0)
    if not frame:
        return False
    obj, UIA = automation()
    el = element(frame)
    cond = obj.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50019)
    try:
        items = el.FindAll(4, cond)
    except Exception:
        return False
    for i in range(items.Length):
        it = items.GetElement(i)
        if (it.CurrentName or "").strip() == tab_name:
            r = it.CurrentBoundingRectangle
            click((r.left + r.right) // 2, (r.top + r.bottom) // 2, settle=0.6)
            import time as _t
            _t.sleep(0.8)
            return True
    return False


def windows_of(pid: int):
    """给 actions 用的窗口列表（转发 win.windows）。"""
    from .win import windows

    return windows(pid)
