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
from .win import (
    ensure_size,
    key,VK, activate, alt_letter, chord, click, close_window, key,
    post_alt_letter, post_ctrl_key,
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
    """解析编译日志（实现放在 inspect 里，这里只做转发，避免两份逻辑漂移）。"""
    from .inspect import read_progress as _rp

    return _rp(gx3)


def read_config(gx3: str | pathlib.Path) -> dict:
    """读 `.gx3` 的 `!!Config.xml`（实现放在 inspect 里）。"""
    from .inspect import read_config as _rc

    return _rc(gx3)


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
        # 先保证窗口是"展开"状态：折叠成 135x37 时菜单栏不存在，Ctrl+N 也不弹窗
        try:
            size = ensure_size(self.main["hwnd"])
            if size.get("invalid"):
                # 句柄失效：重新取主窗，取不到就当没焦点
                fresh = main_window(self.proc.pid, timeout_s=15)
                if not fresh:
                    return False
                self.main = fresh
            elif size.get("restored"):
                self.main = {**self.main, "area": size["area"]}
        except Exception:
            pass
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
    def _alt(self, letter: str) -> None:
        """Alt+字母：优先 PostMessage（可靠），失败再退 SendInput。"""
        if self.main:
            try:
                post_alt_letter(self.main["hwnd"], letter)
                return
            except Exception:
                pass
        alt_letter(letter)

    def _ctrl(self, letter: str, settle: float = 0.8) -> None:
        """Ctrl+字母：用 SendInput。

        实测：PostMessage 投递的 Ctrl+S / Ctrl+N 会被 MFC 的加速键表忽略
        （Alt+字母 反而必须用 PostMessage），所以这里分工明确：
        Alt 系列走 PostMessage，Ctrl 系列走真实按键。
        """
        chord("ctrl", letter, settle)

    def _click_canvas(self) -> None:
        """点一下文档区中心，把焦点从导航栏/下拉框挪开。

        踩过：焦点在导航栏的"全部"下拉框里时，Alt+P 会被控件吃掉，
        菜单不弹、Ctrl+N 也不弹对话框——表现为"新建工程对话框没出现"。
        """
        if not self.main:
            return
        import win32gui
        from .win import click
        try:
            r = win32gui.GetWindowRect(self.main["hwnd"])
        except Exception:
            return
        click(r[0] + int((r[2] - r[0]) * 0.7), r[1] + int((r[3] - r[1]) * 0.55),
              settle=0.4)

    def new_project(self, series: int = 3, model: int = 0, lang: int = 1) -> dict:
        h = None
        seen: list[str] = []
        for attempt in range(5):
            self._focus()
            self._click_canvas()
            # 先试菜单（工程 → 新建），再退回 Ctrl+N：某些启动状态下 Ctrl+N 不响应
            invoked = False
            try:
                self._alt("p")
                time.sleep(0.6)
                invoked = uia.invoke_menu_item("新建(N)")
            except Exception:
                invoked = False
            if not invoked:
                # 菜单还开着的话会把 Ctrl+N 吃掉，先按 ESC 关掉再发
                key("esc")
                time.sleep(0.4)
                self._focus()
                self._ctrl("n", 0.8)
            time.sleep(5.0 + attempt * 2.5)
            for w in self.dialogs():
                title = (w.get("title") or "").strip()
                if title and title not in seen:
                    seen.append(title)
            dlg = next((w for w in self.dialogs() if w["class"] == "#32770"), None)
            if dlg:
                h = dlg["hwnd"]
                break
            self.dismiss(rounds=2)
            time.sleep(1)
        if not h:
            raise RuntimeError("新建工程对话框没出现（已重试 5 次；出现过的对话框=%s）"
                               % seen)
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

    def _save_as_once(self, path: str | pathlib.Path, via_menu: bool = False) -> dict:
        """存到指定路径。

        via_menu=True 时走 `工程 → 另存为(A)`，**即使工程已有路径也会弹对话框**——
        批量场景必须用这个，否则 Ctrl+S 会静默存回旧路径。
        """
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                path.unlink()
            except PermissionError:
                # GX Works3 还开着这个工程，文件被占用：换一个名字存
                for i in range(1, 100):
                    alt = path.with_name(path.stem + "_%d" % i + path.suffix)
                    if not alt.exists():
                        path = alt
                        break
        self._focus()
        # 菜单优先：实测 `Ctrl+S` 在新建工程后经常**不弹**另存为对话框
        # （焦点还在某个控件里），而 `工程 → 另存为(A)`（PostMessage+UIA）稳定弹出。
        self._alt("p")
        time.sleep(0.6)
        opened = uia.invoke_menu_item("另存为(A)") or uia.invoke_menu_item("另存为")
        time.sleep(3.0)
        if not opened:
            self._ctrl("s", 0.8)
            time.sleep(3.5)
        dlg = None
        for _ in range(3):                      # 对话框可能还没画完，重试几次
            dlg = next((w for w in self.dialogs() if w["class"] == "#32770"), None)
            if dlg:
                break
            time.sleep(1.5)
        if not dlg:
            # 已经有路径的工程按 Ctrl+S 是静默保存，不弹对话框；退化成直接保存并校验
            self.dismiss(rounds=2)
            time.sleep(2)
            info = self.save()
            return {"path": str(path), "readback": "(silent-save)",
                    "exists": path.exists(),
                    "bytes": path.stat().st_size if path.exists() else 0,
                    "silent": True}
        edits = []
        for _ in range(4):
            edits = _find_by_cid(dlg["hwnd"], CID_FILENAME, cls="Edit")
            if edits:
                break
            time.sleep(1.2)
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

    def save_as(self, path: str | pathlib.Path, via_menu: bool = False,
                attempts: int = 3) -> dict:
        """另存为：失败就关掉当前对话框、重新发起，最多 attempts 次。

        踩过：壳对话框偶尔还没画完就被找（报“没有文件名输入框”），
        也可能是别的小提示框占了 #32770 —— 所以重试要**重新发起保存**。
        """
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self._save_as_once(path, via_menu)
            except RuntimeError as exc:
                last = exc
                self.dismiss(rounds=2)
                time.sleep(1.5)
                self._focus()
        raise last or RuntimeError("另存为失败")

    def save(self, wait_s: float = 12.0) -> dict:
        """保存并**确认真的写盘了**（mtime 变了才算）。

        踩过：Ctrl+S 之后 4 s 就返回，偶发工程文件没更新（读回来还是空程序）。
        """
        target = pathlib.Path(self.project) if self.project else None
        before = target.stat().st_mtime_ns if target and target.exists() else None
        for attempt in range(3):
            self._focus()
            self._ctrl("s", 0.8)
            t0 = time.time()
            while time.time() - t0 < wait_s:
                time.sleep(1)
                self.dismiss(rounds=2)
                if target and target.exists() and target.stat().st_mtime_ns != before:
                    break
            if target and target.exists() and target.stat().st_mtime_ns != before:
                break
        after = target.stat().st_mtime_ns if target and target.exists() else None
        return {"saved": bool(target and target.exists()),
                "changed": before != after,
                "bytes": target.stat().st_size if target and target.exists() else 0,
                "mtime": target.stat().st_mtime if target and target.exists() else None}

    # ---------- 程序内容 ----------
    def _ensure_main(self) -> dict:
        """每次动作前重取主窗（窗口可能被重建或缩成小尺寸）。"""
        w = main_window(self.proc.pid, 20.0)
        if not w:
            raise RuntimeError("找不到 GX Works3 主窗口")
        if w["area"] < 200000:
            from .win import activate
            activate(w["hwnd"])
            time.sleep(0.8)
            w = main_window(self.proc.pid, 10.0) or w
        self.main = w
        return w

    def paste_st(self, code: str, clear_first: bool = True) -> dict:
        """点进 ST 编辑区（按窗口比例定位），全选后粘贴。"""
        if not self.main:
            raise RuntimeError("会话未启动")
        w = self._ensure_main()
        self._focus()
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

    # ---------- XML 导入 ----------
    def import_xml(self, path: str | pathlib.Path, wait_s: float = 90.0) -> dict:
        """`工程 → 导入文件 → IEC61131-10 XML格式`，并点掉"确定吗？"和完成提示。"""
        path = pathlib.Path(path)
        self._ensure_main()
        self._focus()
        self._alt("p")
        time.sleep(0.7)
        if not uia.invoke_menu_item("导入文件"):
            return {"opened": False, "reason": "菜单项没找到"}
        time.sleep(1.2)
        if not uia.invoke_menu_item("IEC61131-10"):
            return {"opened": False, "reason": "子菜单项没找到"}
        time.sleep(4.5)
        dlg = next((w for w in self.dialogs() if w["class"] == "#32770"), None)
        if not dlg:
            return {"opened": False, "reason": "文件对话框没出现"}
        edits = _find_by_cid(dlg["hwnd"], CID_FILENAME, cls="Edit")
        if not edits:
            return {"opened": False, "reason": "文件名输入框没找到"}
        u32.SendMessageW(edits[0], 0x000C, 0, ctypes.c_wchar_p(str(path)))
        time.sleep(0.6)
        buf = ctypes.create_unicode_buffer(1024)
        u32.SendMessageW(edits[0], 0x000D, 1024, ctypes.byref(buf))
        btns = _find_by_cid(dlg["hwnd"], CID_SAVE_BTN, cls="Button")
        if not btns:
            return {"opened": False, "reason": "打开按钮没找到"}
        import win32con
        import win32gui as wg
        wg.SendMessage(btns[0], win32con.BM_CLICK, 0, 0)
        time.sleep(6)

        # "读取指定文件的内容。确定吗？" → 是(Y)
        from .win import click
        conf = next((w for w in self.dialogs()
                     if w["class"].startswith("WindowsForms10.Window")), None)
        confirmed = False
        if conf:
            btn = uia.button(conf["hwnd"], ("是",))
            if btn:
                click(btn[1], btn[2])
                confirmed = True
                time.sleep(2)

        # 等 "导入XML文件..." 进度结束
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if not any("XML" in w["title"] for w in self.dialogs()):
                break
            time.sleep(1)
        self.dismiss(rounds=3)
        time.sleep(1)
        return {"opened": True, "confirmed": confirmed, "readback": buf.value,
                "seconds": round(time.time() - t0, 1)}

    # ---------- 工程开关（同一会话内切换） ----------
    def close_project(self) -> dict:
        """工程 → 关闭。没有工程时静默返回。"""
        self._focus()
        before = self.title() or ""
        if "工程未设置" in before or before.strip() == "MELSOFT GX Works3":
            return {"closed": False, "reason": "no project", "title": before}
        self._alt("p")
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
        self._ctrl("o", 0.8)
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

    # ---------- 检查类 ----------
    def program_check(self, check_all_programs: bool = True,
                      wait_s: float = 25.0) -> dict:
        """`工具 → 程序检查` → 执行 → 读判定文本（"程序检查已完成。无错误。"）。

        前提：工程已经全部转换过，否则会弹"程序中存在未转换的梯形图…请执行转换"。
        """
        from .uia import automation

        self._ensure_main()
        self._focus()
        self._alt("t")
        time.sleep(0.7)
        opened = uia.invoke_menu_item("程序检查")
        if not opened:
            return {"opened": False, "verdict": None, "errors": None}
        time.sleep(4.5)
        dlg = next((w for w in self.dialogs() if "程序检查" in w["title"]), None)
        if not dlg:
            return {"opened": False, "verdict": None, "errors": None}

        if check_all_programs:
            btn = uia.button(dlg["hwnd"], ("将全部程序作为对象",))
            if btn:
                from .win import click
                click(btn[1], btn[2])

        from .win import click
        run = uia.button(dlg["hwnd"], ("执行",))
        if not run:
            return {"opened": True, "verdict": None, "errors": None}
        click(run[1], run[2])

        verdict = None
        t0 = time.time()
        while time.time() - t0 < wait_s:
            time.sleep(2)
            for name in _uia_names(dlg["hwnd"]):
                if "程序检查已完成" in name or "检查已完成" in name:
                    verdict = name
                    break
            if verdict:
                break
            if not any(w["hwnd"] == dlg["hwnd"] for w in self.dialogs()):
                break

        close = uia.button(dlg["hwnd"], ("关闭",))
        if close:
            click(close[1], close[2])
            time.sleep(1.5)
        self.dismiss(rounds=2)
        errors = None
        if verdict:
            import re as _re
            m = _re.search(r"(\d+)\s*(?:件|处)", verdict)
            if m:
                errors = int(m.group(1))
            elif "无错误" in verdict:
                errors = 0
        return {"opened": True, "verdict": verdict, "errors": errors,
                "clean": bool(verdict and "无错误" in verdict)}


def _uia_names(hwnd: int, limit: int = 2500) -> list[str]:
    from .uia import automation

    out = []
    try:
        auto, _UIA = automation()
        el = uia.element(hwnd)
        items = el.FindAll(4, auto.CreateTrueCondition())   # 4 = Descendants
        for i in range(min(items.Length, limit)):
            try:
                t = (items.GetElement(i).CurrentName or "").strip()
                if t:
                    out.append(t)
            except Exception:
                continue
    except Exception:
        return out
    return out
