"""最小 PDF 解析：页数 / 页面尺寸 / 是否空白。

为什么自己解而不是引库：

* 判据只需要三件事（`docs/JUDGE_SPEC.md` 2.7）：`%PDF-` 头、页数、页面尺寸
  ≈A3；再加一条**非空白**（PDF 出图的经典坑是"出成白纸也返回成功"）；
* 纯标准库（`re` + `zlib`），离线单测和真机跑都用同一份代码，不引入依赖。

「非空白」的判法：把每个 stream 解压（FlateDecode），在解出来的绘图指令里数
`m/l/c/re/S/f/Tj/TJ`。空白页里这些操作符一个都没有 —— 只看"文件存在/有
字节"会把白纸判成功，这正是 spec 明确警告的那条。
"""

from __future__ import annotations

import re
import zlib
from typing import Any, Dict, List, Optional

# A3 = 420 × 297 mm = 1190.551 × 841.89 pt
A3_PT = (1190.551, 841.890)
_OP_NAMES = ("m", "l", "c", "re", "S", "s", "f", "F", "f*", "B", "b", "Tj", "TJ")


def _ops(blob: bytes) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for name in _OP_NAMES:
        pat = rb"(?<![A-Za-z*])" + re.escape(name.encode()) + rb"(?![A-Za-z*])"
        out[name] = len(re.findall(pat, blob))
    return out


def parse(path: str) -> Dict[str, Any]:
    """读一个 PDF，返回页数/尺寸/绘图操作符计数。

    任何一步读不出来都写进 `why` 并保持 `ok=False`，绝不猜。
    """
    out: Dict[str, Any] = {
        "path": path, "bytes": 0, "header": None, "pages": 0,
        "mediabox": None, "size_pt": None, "decoded_bytes": 0,
        "ops": {}, "vector_ops": 0, "text_ops": 0,
        "ok": False, "why": "",
    }
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        out["why"] = "不可读：%s" % (exc,)
        return out
    out["bytes"] = len(data)
    if not data:
        out["why"] = "文件为空"
        return out
    out["header"] = data[:8].decode("latin-1", "replace")
    if not data.startswith(b"%PDF-"):
        out["why"] = "没有 %PDF- 头"
        return out

    out["pages"] = len(re.findall(rb"/Type\s*/Page\b", data))
    boxes = re.findall(
        rb"/MediaBox\s*\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\]",
        data)
    if boxes:
        x0, y0, x1, y1 = (float(v) for v in boxes[0])
        out["mediabox"] = [x0, y0, x1, y1]
        out["size_pt"] = [abs(x1 - x0), abs(y1 - y0)]

    decoded: List[bytes] = []
    for raw in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        blob: Optional[bytes] = None
        try:
            blob = zlib.decompress(raw)
        except zlib.error:
            try:
                blob = zlib.decompressobj().decompress(raw)
            except zlib.error:
                blob = None
        if blob is None:
            # 图片/字体流解不开是正常的；只统计能解的绘图流
            continue
        decoded.append(blob)
    total = b"\n".join(decoded)
    out["decoded_bytes"] = len(total)
    out["ops"] = _ops(total)
    ops = out["ops"]
    out["vector_ops"] = sum(ops[k] for k in ("m", "l", "c", "re", "S", "s",
                                             "f", "F", "f*", "B", "b"))
    out["text_ops"] = ops["Tj"] + ops["TJ"]

    if out["pages"] == 0:
        out["why"] = "没有页（/Type /Page 计数为 0）"
    elif out["size_pt"] is None:
        out["why"] = "读不到 MediaBox"
    elif out["vector_ops"] == 0 and out["text_ops"] == 0:
        out["why"] = "空白页（解压后无任何线条/文字操作符）"
    else:
        out["ok"] = True
    return out


def size_matches_a3(size_pt: Optional[List[float]], tol_pt: float = 2.0) -> bool:
    """页面尺寸是否 A3（横竖都认）。"""
    if not size_pt or len(size_pt) != 2:
        return False
    w, h = sorted(_safe(size_pt), reverse=True)
    a3 = sorted(A3_PT, reverse=True)
    return abs(w - a3[0]) <= tol_pt and abs(h - a3[1]) <= tol_pt


def _safe(vals: List[float]) -> List[float]:
    try:
        return [float(v) for v in vals]
    except (TypeError, ValueError):
        return [0.0, 0.0]
