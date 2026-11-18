"""把模型空间出成单页 PDF（`export.pdf` 的动作层）。

`docs/JUDGE_SPEC.md` 2.7 那条警告（"没显式配布局就出白纸"）在这里对应四步：

1. 设备必须显式设成 PDF 绘图仪（`DWG To PDF.pc3`），否则会打到默认打印机；
2. 介质必须显式设成 A3 —— `CanonicalMediaName` 要从设备实际的介质表里选；
3. `PlotType=1`（acExtents）、`CenterPlot`、`PlotRotation` 要设；
4. **`BACKGROUNDPLOT` 必须临时置 0**：本机实测（2026-10-21）它默认是 2，
   后台出图时 `PlotToFile` 立刻返回 True 但文件要等文档关闭才落盘 ——
   那样"文件存在"就会变成时序赌博。置 0 后同一调用 0.4 s 内落盘。
   用完**必须还原**（它写在配置里、跨会话生效），并读回确认。

动作层只负责"把图出出来 + 把过程记下来"，判据在 `judges/export.py`。
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from . import com

A3_MEDIA = "ISO_A3_(420.00_x_297.00_MM)"
_PDF_DEVICES = ("DWG To PDF.pc3", "AutoCAD PDF (General Documentation).pc3",
                "DWG 转 PDF.pc3")


def _try_busy(fn, warnings, label, attempts: int = 10, delay: float = 0.4):
    """像 _try 一样不抛异常，但对 RPC_E_CALL_REJECTED（出图刚结束很常见）重试。

    实测（2026-11-03）：`PlotToFile` 之后立刻 `SetVariable("BACKGROUNDPLOT", ...)`
    会被 AutoCAD 拒收（-2147418111），紧跟着读回也拒收；旧代码把还原失败当成
    "出图失败"，于是 15 条里偶发一条 FAIL。
    """
    from .com import is_busy_error
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:                    # noqa: BLE001
            last = exc
            if not is_busy_error(exc):
                warnings.append("%s: %s: %s" % (label, type(exc).__name__, exc))
                return None
            time.sleep(delay * (1.0 + i * 0.15))
    warnings.append("%s: COM 一直忙（%s）" % (label, last))
    return None


def _try(fn, warnings: List[str], label: str) -> Any:
    try:
        return fn()
    except Exception as exc:                            # noqa: BLE001
        warnings.append("%s: %s: %s" % (label, type(exc).__name__, exc))
        return None


def plot_model_to_pdf(doc: Any, path: str, *,
                      media: str = A3_MEDIA,
                      timeout_s: float = 60.0,
                      with_plot_styles: bool = True) -> Dict[str, Any]:
    """出一页 A3 PDF。返回过程记录（设备/介质/耗时/背景出图还原情况）。"""
    info: Dict[str, Any] = {
        "path": path, "ok": False, "device": None, "media": None,
        "warnings": [], "elapsed_s": None, "returned": None,
        "backgroundplot_before": None, "backgroundplot_after_restore": None,
        "backgroundplot_restored": False,
    }
    if os.path.exists(path):
        os.remove(path)

    lay = doc.ActiveLayout
    chosen = None
    for cand in _PDF_DEVICES:
        _try(lambda c=cand: setattr(lay, "ConfigName", c),
             info["warnings"], "ConfigName=%s" % cand)
        if str(getattr(lay, "ConfigName", "")) == cand:
            chosen = cand
            break
    info["device"] = chosen or getattr(lay, "ConfigName", None)
    if not chosen:
        # 没有 PDF 绘图仪就**不要**出图：默认设备（如 Microsoft Print to PDF）
        # 会弹文件名对话框，把整轮用例挂死。老老实实判失败。
        info["warnings"].append("没有可用的 PDF 绘图仪（试过 %s）"
                                % ", ".join(_PDF_DEVICES))
        info["ok"] = False
        return info

    medias: List[str] = []
    names = _try(lambda: [str(x) for x in lay.GetCanonicalMediaNames()],
                 info["warnings"], "GetCanonicalMediaNames")
    if names:
        medias = names
    pick = media if media in medias else next(
        (m for m in medias if "A3" in m and "expand" not in m.lower()), None)
    if pick:
        _try(lambda: setattr(lay, "CanonicalMediaName", pick),
             info["warnings"], "CanonicalMediaName")
    info["media"] = _try(lambda: getattr(lay, "CanonicalMediaName"),
                         info["warnings"], "read CanonicalMediaName")
    info["media_available"] = len(medias)

    # with_plot_styles=False 时不要强制打开打印样式表：否则 CTB/STB 会盖掉
    # 对象线宽，"按线宽出图"与"按样式表出图"就没法分开验证（plot.style 需要）。
    for attr, val in (("PlotType", 1), ("CenterPlot", True),
                      ("PlotRotation", 1), ("PlotWithPlotStyles", bool(with_plot_styles))):
        _try(lambda a=attr, v=val: setattr(lay, a, v),
             info["warnings"], attr)

    before = _try(lambda: doc.GetVariable("BACKGROUNDPLOT"),
                  info["warnings"], "GetVariable BACKGROUNDPLOT")
    info["backgroundplot_before"] = before
    if before is not None:
        _try(lambda: doc.SetVariable("BACKGROUNDPLOT", 0),
             info["warnings"], "SetVariable BACKGROUNDPLOT=0")

    t0 = time.time()
    try:
        if chosen:
            info["returned"] = doc.Plot.PlotToFile(path, chosen)
        else:
            info["returned"] = doc.Plot.PlotToFile(path)
    except Exception as exc:                            # noqa: BLE001
        info["warnings"].append("PlotToFile: %s: %s" % (type(exc).__name__, exc))

    deadline = t0 + timeout_s
    while time.time() < deadline:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            info["elapsed_s"] = round(time.time() - t0, 2)
            break
        time.sleep(0.25)

    if before is not None:
        _try_busy(lambda: doc.SetVariable("BACKGROUNDPLOT", before),
                  info["warnings"], "restore BACKGROUNDPLOT")
        after = _try_busy(lambda: doc.GetVariable("BACKGROUNDPLOT"),
                          info["warnings"], "readback BACKGROUNDPLOT")
        info["backgroundplot_after_restore"] = after
        info["backgroundplot_restored"] = (after is not None
                                           and int(after) == int(before))
    else:
        info["warnings"].append("BACKGROUNDPLOT 读不到，无法证明已还原")

    info["ok"] = bool(os.path.exists(path) and os.path.getsize(path) > 0
                      and info["backgroundplot_restored"])
    return info


def save_as(doc: Any, path: str, fmt: Optional[int] = None,
            *, exists_wait_s: float = 15.0,
            make_dirs: bool = False) -> Dict[str, Any]:
    """`SaveAs` 的判据友好封装：等文件真的落盘，返回大小/耗时。"""
    out: Dict[str, Any] = {"path": path, "ok": False, "bytes": 0,
                           "error": None, "elapsed_s": None, "fmt": fmt}
    # 2026-11-18：默认**不再自动建目录**。实测把"父目录不存在"悄悄变成成功，
    # 等于把用户的错路径藏起来（同类病：静默成功）。要建目录请显式 make_dirs=True。
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        if not make_dirs:
            out["error"] = "父目录不存在：%s" % d
            return out
        os.makedirs(d, exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    t0 = time.time()
    # SaveAs 也可能弹框（"替换/另存为"）：新文档的 FILEDIA 来自模板，常常是 1。
    # 这里临时压成 0，保存完再还原——否则 SaveAs 会一直等用户点确定（实测卡死）。
    prev_filedia = None
    try:
        prev_filedia = doc.GetVariable("FILEDIA")
        doc.SetVariable("FILEDIA", 0)
    except Exception:                                   # noqa: BLE001
        prev_filedia = None
    try:
        if fmt is None:
            com.retry(lambda: doc.SaveAs(path), label="SaveAs")
        else:
            com.retry(lambda: doc.SaveAs(path, int(fmt)), label="SaveAs fmt=%s" % fmt)
    except Exception as exc:                            # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    finally:
        if prev_filedia is not None:
            try:
                doc.SetVariable("FILEDIA", prev_filedia)
            except Exception:                           # noqa: BLE001
                pass
    while time.time() - t0 < exists_wait_s:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            break
        time.sleep(0.2)
    out["elapsed_s"] = round(time.time() - t0, 2)
    out["bytes"] = os.path.getsize(path) if os.path.exists(path) else 0
    out["ok"] = out["bytes"] > 0
    if not out["ok"] and out["error"] is None:
        # 实测（2026-11-18）：SaveAs 在"格式码与扩展名不匹配"（如 fmt=65 存 .dwg）
        # 或扩展名不认识时**既不写文件也不抛错**，返回成功。这时必须由我们给出结论，
        # 否则调用方只看到 ok=False、不知道原因，等于静默失败。
        out["error"] = ("SaveAs 未产出文件：fmt=%r 与扩展名 %s 可能不匹配，"
                        "或路径不可写（AutoCAD 未报错，文件 %d 字节）"
                        % (fmt, os.path.splitext(path)[1] or "(无)",
                           out["bytes"]))
    return out
