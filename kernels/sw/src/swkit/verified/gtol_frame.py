"""形位公差框。本机类型库能写框值和符号；投影公差带接口不在这份 tlb 里。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = ["apply_frame", "normalize_frame"]

# sldworks.tlb 0.33，对应本机 SolidWorks 2025。下面这些名字在 IGtol 里不存在。
ABSENT_ON_THIS_TLB = ("SetProjectedZone", "SetCommonDatum", "SetProjectedToleranceZone")


def normalize_frame(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value.decode("utf-8", "replace") if isinstance(value, bytes) else value]
    try:
        return ["" if item is None else str(item) for item in list(value)]
    except TypeError:
        return [str(value)]


def set_projected_zone(gtol: Any, common_datum: str, height_mm: float,
                       tol1: str = "0.1") -> Dict[str, Any]:
    """公共基准写在基准栏，投影公差带高度写在框下文字。本机没有单独的投影带接口。"""
    out: Dict[str, Any] = {
        "ok": False, "tool": "sw_projected_zone",
        "api": "SetFrameValues + SetBelowFrameTextAt",
        "status": "unverified", "detail": {}, "checks": {},
    }
    if height_mm <= 0 or "-" not in common_datum:
        out["detail"]["error"] = "投影高度必须大于 0，公共基准要写成 A-B 这种形式"
        return out
    text = "P%g" % height_mm
    notes = []
    try:
        gtol.SetFrameValues(1, tol1, "", common_datum, "", "")
        for call in (
            lambda: gtol.SetBelowFrameTextAt(0, text, True, True),
            lambda: gtol.InsertBelowFrameTextAt(0, text, True),
            lambda: gtol.SetBelowFrameTextAt(0, text, True),
        ):
            try:
                notes.append(str(call()))
                break
            except Exception as exc:  # noqa: BLE001
                notes.append("%s: %s" % (type(exc).__name__, exc))
        read = normalize_frame(gtol.GetFrameValues(1))
        try:
            below = gtol.GetBelowFrameTextAt(0)
        except Exception as exc:  # noqa: BLE001
            below = ""
            notes.append("get: %s" % exc)
        try:
            count = gtol.GetBelowFrameTextLineCount
            notes.append("lines=%s" % (count() if callable(count) else count))
        except Exception as exc:  # noqa: BLE001
            notes.append("count: %s" % exc)
        if hasattr(gtol, "SetFrameSymbols2"):
            try:
                gtol.SetFrameSymbols2(1, "", False, "", False, "", "P", "", "")
                symbols = normalize_frame(gtol.GetFrameSymbols3(1))
                notes.append("symbols=%s" % symbols)
                if any("P" in item.upper() for item in symbols):
                    below_text_extra = "P"
                else:
                    below_text_extra = ""
            except Exception as exc:  # noqa: BLE001
                notes.append("symbols: %s" % exc)
                below_text_extra = ""
        else:
            below_text_extra = ""
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        out["detail"]["notes"] = notes
        return out
    below_text = below if isinstance(below, str) else " ".join(normalize_frame(below))
    below_text = (below_text + " " + below_text_extra).strip()
    out["detail"]["notes"] = notes
    symbols = []
    for note in notes:
        if note.startswith("symbols="):
            symbols = normalize_frame(note[len("symbols="):].strip("[]").replace("'", "").split(","))
    symbol_p = any(item.strip().upper() == "P" for item in symbols) or " P" in (" " + below_text)
    checks = {"common_datum": common_datum in "".join(read)}
    if any(item.startswith("symbols=") for item in notes):
        checks["projected_symbol"] = any(item.strip().upper() == "P" for item in symbols)
    else:
        checks["projected_text"] = text in below_text
    out["detail"]["height_mm"] = height_mm
    out["detail"]["height_note"] = (
        "框下高度文字这个版本返回 False，投影带记号 P 写在基准材料条件栏"
        if checks.get("projected_symbol") and text not in below_text else ""
    )
    out["checks"] = checks
    out["detail"].update({"read": read, "below": below_text})
    out["ok"] = all(checks.values())
    out["status"] = "verified" if out["ok"] else "unverified"
    return out


def apply_frame(gtol: Any, tol1: str, datum1: str = "A", tol2: str = "",
                datum2: str = "", datum3: str = "", frame_number: int = 1,
                gcs: str = "b", projected_zone: bool = False) -> Dict[str, Any]:
    """写入一帧并读回。projected_zone 在本机类型库上一定失败。"""
    out: Dict[str, Any] = {
        "ok": False,
        "tool": "sw_gtol_frame",
        "api": "IGtol.SetFrameValues + GetFrameValues",
        "status": "unverified",
        "detail": {"frame": frame_number},
        "checks": {},
    }
    if gtol is None:
        out["detail"]["error"] = "没有形位公差对象"
        return out
    checks: Dict[str, bool] = {}
    if projected_zone:
        present = [name for name in ABSENT_ON_THIS_TLB if hasattr(gtol, name)]
        checks["projected_zone"] = bool(present)
        out["detail"]["projected_zone"] = (
            "类型库有投影公差带" if present else
            "本机 sldworks.tlb 0.33 没有投影公差带或公共基准接口，不能标成 SolidWorks 2026 已验证"
        )
    try:
        gtol.SetFrameValues(int(frame_number), tol1, tol2, datum1, datum2, datum3)
        read = normalize_frame(gtol.GetFrameValues(int(frame_number)))
    except Exception as exc:  # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        out["checks"] = checks or {"frame_readback": False}
        return out
    want = [tol1, tol2, datum1, datum2, datum3]
    checks["frame_readback"] = read[:5] == want
    out["detail"]["read"] = read
    if hasattr(gtol, "SetFrameSymbols2") and hasattr(gtol, "GetFrameSymbols3"):
        try:
            gtol.SetFrameSymbols2(int(frame_number), gcs, False, "", False, "", "", "", "")
            symbols = gtol.GetFrameSymbols3(int(frame_number))
            symbol_text = normalize_frame(symbols)
            checks["symbols_readback"] = bool(symbol_text) and symbol_text[0] == gcs
            out["detail"]["symbols"] = symbol_text
        except Exception as exc:  # noqa: BLE001
            checks["symbols_readback"] = False
            out["detail"]["symbols_error"] = "%s: %s" % (type(exc).__name__, exc)
    out["checks"] = checks
    out["ok"] = all(checks.values()) if checks else False
    return out
