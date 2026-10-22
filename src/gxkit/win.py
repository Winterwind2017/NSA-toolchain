"""Win32 / UIA 驱动层：GX Works3 没有 COM，只能靠硬件级消息与真实鼠标键盘。

这里只放"跟业务无关"的底层：找窗口、点坐标、敲键、读写剪贴板、枚举对话框。
"""

from __future__ import annotations

import ctypes
import time

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

# 64 位下必须显式声明，否则句柄被截断成 int32（曾导致 GlobalLock 返回 NULL）
k32.GlobalAlloc.restype = ctypes.c_void_p
k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = [ctypes.c_void_p]
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
u32.OpenClipboard.argtypes = [ctypes.c_void_p]
u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
u32.SetClipboardData.restype = ctypes.c_void_p
u32.SendMessageW.restype = ctypes.c_long

VK = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "enter": 0x0D, "esc": 0x1B,
    "tab": 0x09, "down": 0x28, "up": 0x26, "f4": 0x73, "del": 0x2E,
}

# 这些对话框不能点"关闭/取消"——会把正要保存的东西一起关掉
KEEP_OPEN = ("另存为", "打开", "导入文件", "保存")


def windows(pid: int, visible_only: bool = True) -> list[dict]:
    import win32gui
    import win32process

    out = []

    def cb(hwnd, _):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        if wpid != pid:
            return
        if visible_only and not win32gui.IsWindowVisible(hwnd):
            return
        r = win32gui.GetWindowRect(hwnd)
        out.append({"hwnd": hwnd, "title": win32gui.GetWindowText(hwnd),
                    "class": win32gui.GetClassName(hwnd), "rect": list(r),
                    "area": (r[2] - r[0]) * (r[3] - r[1])})

    win32gui.EnumWindows(cb, None)
    return sorted(out, key=lambda w: w["area"], reverse=True)


def main_window(pid: int, timeout_s: float = 120.0) -> dict | None:
    """等主窗口。注意：窗口可能以最小化/很小尺寸出现，不能只按面积筛。"""
    import win32gui

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        cands = [w for w in windows(pid) if w["class"] == "GXW3FrameWnd"]
        if cands:
            best = max(cands, key=lambda w: w["area"])
            if best["area"] < 100000:
                # 最小化或异常尺寸：还原后再量一次
                u32.ShowWindow(best["hwnd"], 9)     # SW_RESTORE
                time.sleep(0.8)
                again = [w for w in windows(pid) if w["hwnd"] == best["hwnd"]]
                if again:
                    best = again[0]
            return best
        time.sleep(0.4)
    return None


def click(x: int, y: int, settle: float = 0.5) -> None:
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    u32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    u32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(settle)


def key(vk: int, up: bool = False) -> None:
    u32.keybd_event(vk, 0, 2 if up else 0, 0)


def _vk(name_or_vk) -> int:
    if isinstance(name_or_vk, int):
        return name_or_vk
    key_name = str(name_or_vk)
    if key_name in VK:
        return VK[key_name]
    if len(key_name) == 1:
        return ord(key_name.upper())
    raise KeyError("未知按键：%r" % (name_or_vk,))


def tap(name_or_vk, wait: float = 0.3) -> None:
    vk = _vk(name_or_vk)
    key(vk)
    time.sleep(0.07)
    key(vk, up=True)
    time.sleep(wait)


def chord(mods: str, name_or_vk, wait: float = 0.6) -> None:
    """chord('ctrl', 'v') / chord('shift+alt', 'f4')"""
    mod_list = [m.strip() for m in mods.split("+") if m.strip()]
    for m in mod_list:
        key(VK[m])
    time.sleep(0.08)
    tap(name_or_vk, 0.15)
    for m in reversed(mod_list):
        key(VK[m], up=True)
    time.sleep(wait)


def alt_letter(letter: str, wait: float = 0.5) -> None:
    key(VK["alt"])
    time.sleep(0.1)
    tap(ord(letter.upper()), 0.45)
    key(VK["alt"], up=True)
    time.sleep(wait)


def set_clipboard(text: str) -> None:
    CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
    data = text.encode("utf-16-le") + b"\x00\x00"
    h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not h:
        raise OSError("GlobalAlloc failed")
    p = k32.GlobalLock(h)
    if not p:
        raise OSError("GlobalLock failed")
    ctypes.memmove(p, data, len(data))
    k32.GlobalUnlock(h)
    for _ in range(10):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.2)
    u32.EmptyClipboard()
    u32.SetClipboardData(CF_UNICODETEXT, h)
    u32.CloseClipboard()


def wait_gone(predicate, timeout_s: float = 120.0, poll_s: float = 1.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if not predicate():
            return True
        time.sleep(poll_s)
    return False


def close_window(hwnd: int) -> None:
    import win32con
    import win32gui

    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception:
        pass


def activate(hwnd: int, settle: float = 0.5) -> bool:
    """把窗口真正提到前台。

    SetForegroundWindow 对"不是刚启动的进程"经常被 Windows 拒绝（返回 0，后台不动），
    此时 Alt 菜单、Ctrl+N 全部无效——表现为"点了没反应"，很容易误判成功能不可用。
    这里用 SwitchToThisWindow + 点标题栏双保险，并返回是否真的到了前台。
    """
    import win32gui

    u32.ShowWindow(hwnd, 9)          # SW_RESTORE
    try:
        u32.SwitchToThisWindow(hwnd, True)
    except Exception:
        pass
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    if u32.GetForegroundWindow() != hwnd:
        try:
            r = win32gui.GetWindowRect(hwnd)
            click((r[0] + r[2]) // 2, r[1] + 12, 0.4)
        except Exception:
            pass
        u32.SetForegroundWindow(hwnd)
        time.sleep(0.3)
    time.sleep(settle)
    return u32.GetForegroundWindow() == hwnd
