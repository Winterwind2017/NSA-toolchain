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
