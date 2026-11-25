"""只抓 SolidWorks 自己的窗口。桌面、别的进程、零个或多于一个窗口都拒绝。"""

from __future__ import annotations

import os
import struct
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = ["choose_window", "write_bmp", "capture_solidworks", "burst"]


def choose_window(windows: Iterable[Dict[str, Any]], desktop_hwnd: int = 0) -> Tuple[Optional[Dict[str, Any]], str]:
    hits = []
    for item in windows:
        hwnd = int(item.get("hwnd") or 0)
        process = os.path.basename(str(item.get("process") or "")).lower()
        title = str(item.get("title") or "").upper()
        if hwnd <= 0 or hwnd == int(desktop_hwnd):
            continue
        if process != "sldworks.exe":
            continue
        if "SOLIDWORKS" not in title and "SLDWORKS" not in title:
            continue
        hits.append(item)
    if len(hits) != 1:
        return None, "需要且只能有一个 SOLIDWORKS 窗口，实际 %d 个" % len(hits)
    return hits[0], ""


def write_bmp(path: str, width: int, height: int, bgr_rows: Sequence[bytes]) -> None:
    if width <= 0 or height <= 0 or len(bgr_rows) != height:
        raise ValueError("位图尺寸不对")
    row_stride = (width * 3 + 3) & ~3
    pixels = bytearray()
    for row in reversed(bgr_rows):
        if len(row) != width * 3:
            raise ValueError("行宽不对")
        pixels.extend(row)
        pixels.extend(b"\x00" * (row_stride - width * 3))
    header = struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(header + info + pixels)


def _windows_from_desktop() -> Tuple[List[Dict[str, Any]], int]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    desktop = int(user32.GetDesktopWindow())
    rows: List[Dict[str, Any]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process = ""
        access = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
        handle = kernel32.OpenProcess(access, False, pid.value)
        if handle:
            name = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(260)
            if kernel32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
                process = name.value
            kernel32.CloseHandle(handle)
        rows.append({"hwnd": int(hwnd), "title": buf.value, "process": process})
        return True

    user32.EnumWindows(visit, 0)
    return rows, desktop


def capture_solidworks(path: str, windows: Optional[Iterable[Dict[str, Any]]] = None,
                       desktop_hwnd: int = 0) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": False, "tool": "sw_preview_frame", "api": "PrintWindow",
        "status": "unverified", "detail": {}, "checks": {},
    }
    if windows is None:
        windows, desktop_hwnd = _windows_from_desktop()
    chosen, reason = choose_window(windows, desktop_hwnd)
    if chosen is None:
        out["detail"]["error"] = reason
        out["checks"] = {"one_solidworks_window": False, "not_desktop": True}
        return out
    hwnd = int(chosen["hwnd"])
    out["detail"]["hwnd"] = hwnd
    out["detail"]["title"] = chosen.get("title")
    try:
        width, height = _print_window(hwnd, path)
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        out["checks"] = {"one_solidworks_window": True, "bmp_written": False}
        return out
    magic = b""
    size = 0
    if os.path.isfile(path):
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            magic = handle.read(2)
    checks = {
        "one_solidworks_window": True,
        "not_desktop": hwnd != int(desktop_hwnd) and hwnd > 0,
        "bmp_written": magic == b"BM" and size > 54 and width > 1 and height > 1,
    }
    out["checks"] = checks
    out["detail"].update({"width": width, "height": height, "bytes": size})
    out["ok"] = all(checks.values())
    return out


def burst(directory: str, frames: int = 3, windows: Optional[Iterable[Dict[str, Any]]] = None,
          desktop_hwnd: int = 0) -> Dict[str, Any]:
    if frames < 1:
        raise ValueError("帧数至少为 1")
    os.makedirs(directory, exist_ok=True)
    rows = []
    for index in range(frames):
        path = os.path.join(directory, "frame_%03d.bmp" % index)
        rows.append(capture_solidworks(path, windows=windows, desktop_hwnd=desktop_hwnd))
    return {
        "ok": all(item["ok"] for item in rows),
        "tool": "sw_preview_burst",
        "frames": rows,
        "checks": {"every_frame_ok": all(item["ok"] for item in rows)},
    }


def _print_window(hwnd: int, path: str) -> Tuple[int, int]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetWindowRect 失败")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 2 or height < 2:
        raise RuntimeError("窗口面积太小")
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mem, bitmap)
    printed = user32.PrintWindow(hwnd, mem, 2)
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    raw = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem, bitmap, 0, height, raw, ctypes.byref(info), 0)
    rows = []
    for y in range(height):
        start = y * width * 4
        bgra = raw.raw[start:start + width * 4]
        row = bytearray()
        for i in range(width):
            row.extend(bgra[i * 4:i * 4 + 3])
        rows.append(bytes(row))
    write_bmp(path, width, height, rows)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    if not printed:
        raise RuntimeError("PrintWindow 失败")
    return width, height
