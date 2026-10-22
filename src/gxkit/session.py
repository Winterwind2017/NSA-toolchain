"""GX Works3 会话：把"人在界面上做的动作"封装成可重复调用的一组方法。

没有 COM，因此每一步都是真实鼠标/键盘；每个动作都靠**读回**确认（读控件值、
读工程文件、读编译日志），不信任返回值。
"""

from __future__ import annotations

import ctypes
import json
import pathlib
import re
import subprocess
import time
import zipfile

from . import uia
from .win import (VK, activate, alt_letter, chord, click, close_window, key,
                  main_window, set_clipboard, tap, windows)

EXE = r"D:\Program Files (x86)\MELSOFT\GPPW3\GXW3.exe"

# 新建工程对话框的控件 id（日文版 GX Works3 1.117 实测）
CID_SERIES = 537      # 系列：0 MX控制 1 RCPU 2 LHCP 3 FX5C 4 QCPU 5 LCPU 6 FXCP 7 NCCP
CID_MODEL = 540       # 机型：随系列变；FX5C 下是 FX5U/FX5U/FX5S
CID_RUNMODE = 672     # 运行模式
CID_LANG = 542        # 程序语言：0 梯形图 1 ST 2 SFC 3 FBD/ 4 不指定

CID_FILENAME = 1148   # 另存为/打开 对话框的文件名 Edit
CID_SAVE_BTN = 1

CB_SETCURSEL, CBN_SELCHANGE = 0x014E, 1

KEEP_OPEN_TITLES = ("另存为", "打开", "导入文件", "保存")

u32 = ctypes.windll.user32


def _find_by_cid(parent: int, cid: int, cls: str | None = None,
                 text_contains: str | None = None) -> list[int]:
    """按控件 id 找子窗口。

    壳对话框里 cid 会撞车：文件名 Edit(1148) 同时存在于 ComboBoxEx32/ComboBox/Edit，
    保存按钮(1) 会跟 FolderView 列表撞上——所以必须再按类名/文本过滤。
    """
    import win32gui

    out = []

    def cb(h, _):
        if win32gui.GetDlgCtrlID(h) != cid:
            return
        if cls is not None and win32gui.GetClassName(h) != cls:
            return
        if text_contains is not None and text_contains not in win32gui.GetWindowText(h):
            return
        out.append(h)

    win32gui.EnumChildWindows(parent, cb, None)
    return out


def _combo_state(hwnd: int) -> dict:
    n = u32.SendMessageW(hwnd, 0x0146, 0, 0)     # CB_GETCOUNT
    cur = u32.SendMessageW(hwnd, 0x0147, 0, 0)   # CB_GETCURSEL
    items = []
    for i in range(max(0, n)):
        ln = u32.SendMessageW(hwnd, 0x0149, i, 0)  # CB_GETLBTEXTLEN
        buf = ctypes.create_unicode_buffer(max(ln + 1, 2))
        u32.SendMessageW(hwnd, 0x0148, i, ctypes.byref(buf))  # CB_GETLBTEXT
        items.append(buf.value)
    return {"count": n, "current": cur, "items": items}


def _set_combo(dlg: int, combo: int, cid: int, index: int) -> None:
    u32.SendMessageW(combo, CB_SETCURSEL, index, 0)
    time.sleep(0.15)
    u32.SendMessageW(dlg, 0x0111, (CBN_SELCHANGE << 16) | (cid & 0xFFFF), combo)
    time.sleep(1.0)


def read_progress(gx3: str | pathlib.Path) -> dict:
    """解析工程里的 ConvertData/Progress.txt（编译日志，纯文本，最可靠的判据）。"""
    p = pathlib.Path(gx3)
    out = {"found": False, "errors": None, "warnings": None, "stages": [], "raw": ""}
    if not p.exists():
        return out
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.endswith("Progress.txt")]
        if not names:
            return out
        text = z.read(names[0]).decode("utf-8", "replace")
    out["found"] = True
    out["raw"] = text[-2000:]
    stages = re.findall(r"^(.*?)\.\.\.\r?\nError:(\d+),Warning:(\d+)", text, re.M)
    out["stages"] = [{"stage": s.strip(), "errors": int(e), "warnings": int(w)}
                     for s, e, w in stages]
    m = re.search(r"错误：(\d+)、警告：(\d+)", text)
    if m:
        out["errors"], out["warnings"] = int(m.group(1)), int(m.group(2))
    return out


def read_config(gx3: str | pathlib.Path) -> dict:
    """读 .gx3 里的 !!Config.xml（Unit / UnitId / Title）。"""
    p = pathlib.Path(gx3)
    out = {}
    if not p.exists():
        return out
    with zipfile.ZipFile(p) as z:
        raw = z.read("!!Config.xml").decode("utf-8-sig", "replace")
    for attr in ("Unit", "UnitId", "Title", "SecurityVersion"):
        m = re.search(r'%s="([^"]*)"' % attr, raw)
        if m:
            out[attr] = m.group(1)
    return out


class Session:
    def __init__(self, exe: str = EXE, project: str | None = None, timeout_s: float = 120.0):
        self.exe = exe
        self.project = project
        self.proc: subprocess.Popen | None = None
        self.main: dict | None = None
        self.log: list[dict] = []
        self.timeout_s = timeout_s

    # ---------- 生命周期 ----------
    def start(self) -> dict:
        last = None
        for attempt in range(2):
            args = [self.exe] + ([str(self.project)] if self.project else [])
            self.proc = subprocess.Popen(args, cwd=str(pathlib.Path(self.exe).parent))
            uia.bind_pid(self.proc.pid)
            t0 = time.time()
            self.main = main_window(self.proc.pid, 180.0)
            if self.main:
                break
            last = {"attempt": attempt + 1, "rc": self.proc.poll(),
                    "windows": [(w["title"], w["class"]) for w in windows(self.proc.pid)][:5]}
            if self.proc.poll() is None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)],
                               capture_output=True)
            time.sleep(3)
        if not self.main:
            raise RuntimeError("GX Works3 主窗口没起来：%r" % (last,))
        self.log.append({"action": "start", "pid": self.proc.pid,
                         "startup_s": round(time.time() - t0, 1)})
        time.sleep(6)   # 启动画面/欢迎页
        self._focus()
        # 上一次被强杀后可能弹"恢复/错误报告"之类的对话框，先清掉再干活
        self.dismiss(rounds=2)
        return {"pid": self.proc.pid, "startup_s": round(time.time() - t0, 1),
                "title": self.title()}

    def _focus(self) -> bool:
        """返回是否真的拿到了前台焦点（拿不到就别发按键，否则一切"没反应"）。"""
        if not self.main:
            return False
        ok = activate(self.main["hwnd"])
        self.log.append({"action": "focus", "ok": ok})
        return ok

    def title(self) -> str | None:
        if not self.main:
            return None
        for w in windows(self.proc.pid):
            if w["hwnd"] == self.main["hwnd"]:
                return w["title"]
        return None

    def close(self) -> dict:
        res = {"closed": False, "killed": False}
        if not self.proc:
            return res
        if self.main:
            close_window(self.main["hwnd"])
        for _ in range(30):
            if self.proc.poll() is not None:
                res["closed"] = True
                break
            time.sleep(1)
        if self.proc.poll() is None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)],
                           capture_output=True)
            res["killed"] = True
        return res

    # ---------- 对话框 ----------
    def dialogs(self) -> list[dict]:
        return [w for w in windows(self.proc.pid)
                if w["class"] not in ("GXW3FrameWnd", "XTPPopupBar") and w["area"] > 20000]

    def dismiss(self, rounds: int = 6, accept: tuple[str, ...] = ("确定", "是", "OK")) -> list[dict]:
        """点掉阻塞提示框（确定/是）。保存/打开这类要保留的对话框不动。"""
        acted = []
        for _ in range(rounds):
            hit = False
            for w in self.dialogs():
                if any(t in w["title"] for t in KEEP_OPEN_TITLES):
                    continue
                btn = uia.button(w["hwnd"], accept)
                if btn:
                    name, x, y = btn
                    click(x, y)
                    acted.append({"title": w["title"], "class": w["class"], "button": name})
                    time.sleep(1.2)
                    hit = True
                    break
            if not hit:
                break
        self.log.extend(acted)
        return acted

    def wait_xml_progress(self, timeout_s: float = 120.0) -> bool:
        def busy():
            return any("XML" in w["title"] for w in windows(self.proc.pid))
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if not busy():
                return True
            time.sleep(1)
        return False

    # ---------- 工程 ----------
    def new_project(self, series: int = 3, model: int = 0, lang: int = 1) -> dict:
        h = None
        for attempt in range(3):
            self._focus()
            # 先试菜单（工程 → 新建），再退回 Ctrl+N：某些启动状态下 Ctrl+N 不响应
            invoked = False
            try:
                alt_letter("p")
                time.sleep(0.6)
                invoked = uia.invoke_menu_item("新建(N)")
            except Exception:
                invoked = False
            if not invoked:
                chord("ctrl", "n", 0.8)
            time.sleep(4.5 + attempt * 2)
            dlg = next((w for w in self.dialogs() if w["class"] == "#32770"), None)
            if dlg:
                h = dlg["hwnd"]
                break
            self.dismiss(rounds=2)
            time.sleep(1)
        if not h:
            raise RuntimeError("新建工程对话框没出现（已重试 3 次）")
        combos = {}
        for cid in (CID_SERIES, CID_MODEL, CID_RUNMODE, CID_LANG):
            hs = _find_by_cid(h, cid)
            if hs:
                combos[cid] = hs[0]
        state = {}
        for cid, index in ((CID_SERIES, series), (CID_MODEL, model), (CID_LANG, lang)):
            if cid in combos:
                _set_combo(h, combos[cid], cid, index)
                state[cid] = _combo_state(combos[cid])
        u32.SendMessageW(h, 0x0111, CID_SAVE_BTN, 0)   # 确定
        time.sleep(5)
        self.dismiss(rounds=3)                          # "添加模块"提示
        time.sleep(1)
        return {"title": self.title(), "combos": {str(k): v for k, v in state.items()}}

    def save_as(self, path: str | pathlib.Path) -> dict:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        self._focus()
        chord("ctrl", "s", 0.8)
        time.sleep(3.5)
        dlg = next((w for w in self.dialogs() if w["class"] == "#32770"), None)
        if not dlg:
            # 已经有路径的工程按 Ctrl+S 是静默保存，不弹对话框；退化成直接保存并校验
            self.dismiss(rounds=2)
            time.sleep(2)
            info = self.save()
            return {"path": str(path), "readback": "(silent-save)",
                    "exists": path.exists(),
                    "bytes": path.stat().st_size if path.exists() else 0,
                    "silent": True}
        edits = _find_by_cid(dlg["hwnd"], CID_FILENAME, cls="Edit")
        if not edits:
            raise RuntimeError("另存为对话框里没有文件名输入框")
        u32.SendMessageW(edits[0], 0x000C, 0, ctypes.c_wchar_p(str(path)))   # WM_SETTEXT
        time.sleep(0.7)
        buf = ctypes.create_unicode_buffer(1024)
        u32.SendMessageW(edits[0], 0x000D, 1024, ctypes.byref(buf))          # WM_GETTEXT
        readback = buf.value
        btns = _find_by_cid(dlg["hwnd"], CID_SAVE_BTN, cls="Button")
        if not btns:
            raise RuntimeError("另存为对话框里没有保存按钮")
        import win32con
        import win32gui as wg
        wg.SendMessage(btns[0], win32con.BM_CLICK, 0, 0)
        time.sleep(5)
        self.dismiss(rounds=3)      # "标准/压缩格式"提示 → 是
        time.sleep(1.5)
        return {"path": str(path), "readback": readback, "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0}

    def save(self) -> dict:
        self._focus()
        chord("ctrl", "s", 0.8)
        time.sleep(4)
        self.dismiss(rounds=3)
        time.sleep(1)
        if not self.project:
            return {"saved": False}
        p = pathlib.Path(self.project)
        return {"saved": True, "bytes": p.stat().st_size if p.exists() else 0,
                "mtime": p.stat().st_mtime if p.exists() else None}

    # ---------- 程序内容 ----------
    def paste_st(self, code: str, clear_first: bool = True) -> dict:
        """点进 ST 编辑区（按窗口比例定位），全选后粘贴。"""
        if not self.main:
            raise RuntimeError("会话未启动")
        self._focus()
        w = next((x for x in windows(self.proc.pid) if x["hwnd"] == self.main["hwnd"]), None)
        L, T, R, B = w["rect"]
        x = L + int((R - L) * 0.45)
        y = T + int((B - T) * 0.45)
        click(x, y)
        if clear_first:
            chord("ctrl", "a", 0.4)
        set_clipboard(code)
        chord("ctrl", "v", 1.2)
        time.sleep(1.5)
        return {"clicked": [x, y], "chars": len(code), "title": self.title()}

    def convert_all(self, wait_s: float = 10.0) -> dict:
        self._focus()
        chord("shift+alt", "f4", 0.6)
        time.sleep(wait_s)
        self.dismiss(rounds=4)
        time.sleep(1)
        return {"title": self.title()}

    def steps(self) -> int | None:
        """从标题里的 "[... N步]" 读步数（没有就 None）。"""
        t = self.title() or ""
        m = re.search(r"(\d+)步", t)
        return int(m.group(1)) if m else None

    # ---------- 工程开关（同一会话内切换） ----------
    def close_project(self) -> dict:
        """工程 → 关闭。没有工程时静默返回。"""
        self._focus()
        before = self.title() or ""
        if "工程未设置" in before or before.strip() == "MELSOFT GX Works3":
            return {"closed": False, "reason": "no project", "title": before}
        alt_letter("p")
        time.sleep(0.6)
        ok = uia.invoke_menu_item("关闭(C)")
        time.sleep(3)
        self.dismiss(rounds=2)
        time.sleep(1)
        return {"closed": bool(ok), "title": self.title()}

    def open_project(self, path: str | pathlib.Path, wait_s: float = 25.0) -> bool:
        """Ctrl+O 打开工程，等标题里出现文件名。"""
        path = pathlib.Path(path)
        self._focus()
        chord("ctrl", "o", 0.8)
        time.sleep(3.5)
        dlg = next((w for w in self.dialogs() if w["class"] == "#32770"), None)
        if not dlg:
            return False
        edits = _find_by_cid(dlg["hwnd"], CID_FILENAME, cls="Edit")
        if not edits:
            return False
        u32.SendMessageW(edits[0], 0x000C, 0, ctypes.c_wchar_p(str(path)))
        time.sleep(0.5)
        btns = _find_by_cid(dlg["hwnd"], 1, cls="Button", text_contains="打开")
        if not btns:
            btns = _find_by_cid(dlg["hwnd"], 1, cls="Button")
        if not btns:
            return False
        import win32con
        import win32gui as wg
        wg.SendMessage(btns[0], win32con.BM_CLICK, 0, 0)
        t0 = time.time()
        while time.time() - t0 < wait_s:
            time.sleep(1)
            if path.name in (self.title() or ""):
                self.dismiss(rounds=2)
                return True
        self.dismiss(rounds=2)
        return path.name in (self.title() or "")
