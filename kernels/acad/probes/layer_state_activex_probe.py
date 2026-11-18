# -*- coding: utf-8 -*-
"""证据复现：ActiveX 下 `-LAYERSTATE` 为什么不可交付（不是发布代码）。

从 `src/acadkit/build/layer.py` 移出（2026-11-18）。原因有两个：
1. 它已经没有调用方（`layer.state` 能力改走 .NET 通道的 `LayerStateManager`）；
2. 它含 `-LAYERSTATE`，而 `tools/parity_scan.py` 会拦截"程序化路径里的弹框/阻塞命令"。

保留它是为了**可复现**：谁要复核"是不是真的卡死"，跑这个函数即可。
放 `probes/` 而不是 `build/`，因为它不参与任何能力。

用法：
    python -c "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'probes'); \
               import layer_state_activex_probe"   # 见文件末尾的 __main__ 说明
"""

from __future__ import annotations

from typing import Any, Dict

from acadkit.build.helpers import ms_of, pt, add
from acadkit.build.layer import _ensure_layer, _p, _trace, send


def build_layer_state(doc: Any, ctx: Dict[str, Any]) -> None:
    """图层状态：保存 → 删图层 → 恢复。

    ★ 本机实测（2026-10-21）：`-LAYERSTATE` 在 COM 下不可交付 ——
    只要**动过图层表**（COM 建层、entmake 建层、甚至 SaveAs 之后），
    Save 就永久卡在命令提示符（SendCommand / LISP `command` / `vl-cmdf` 全试过）；
    没动过图层表时能返回，但本用例必然要动图层表。所以内核改用
    :func:`build_layer_snapshot`（属性级快照），本函数保留作证据复现。
    """
    name = str(_p(ctx, "name", "03_STATE"))
    color = int(_p(ctx, "color", 5))
    state = str(_p(ctx, "state", "ACADKIT_STATE"))
    _ensure_layer(doc, name, color)
    _trace("layer created")
    send(doc, '(vl-cmdf "_.-LAYERSTATE" "_Save" "%s")' % state, settle=0.8)
    _trace("state saved")
    count_before = int(doc.Layers.Count)
    deleted = False
    try:
        doc.Layers.Item(name).Delete()
        deleted = True
        _trace("layer deleted")
    except Exception as exc:                        # noqa: BLE001
        ctx["notes"].append("删图层失败：%s: %s" % (type(exc).__name__, exc))
    count_after_delete = int(doc.Layers.Count)
    send(doc, '(vl-cmdf "_.-LAYERSTATE" "_Restore" "%s")' % state, settle=1.0)
    _trace("state restored")
    count_after_restore = int(doc.Layers.Count)
    ctx.setdefault("artifacts", {})["layer_state"] = {
        "name": name, "color": color, "state": state, "deleted": deleted,
        "count_before": count_before,
        "count_after_delete": count_after_delete,
        "count_after_restore": count_after_restore,
    }


if __name__ == "__main__":              # 手动复现（会真的卡死，谨慎）
    print("把本函数接到一个文档对象上执行即可复现 -LAYERSTATE 卡提示符。")
