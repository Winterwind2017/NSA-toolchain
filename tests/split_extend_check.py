"""tests/split_extend_check.py —— 分割实体 / 草图延伸：把"调不通"的事实固化

分割实体（`sw_split_body`）：

* `PreSplitBody2` 是**属性**，能算出 2 个分割体（说明刀具被识别）
* 但 `PostSplitBody2` 在下列 6 种参数封装下都返回 **None**，且几何不变：
  - `ConsumeCut` = True / False
  - `BodiesToMark` = tuple / list / `VARIANT(VT_ARRAY|VT_VARIANT)` / 单个体
  - `Origins`/`SavePaths` = 长度匹配的空值数组 / `VARIANT(VT_ARRAY|VT_BSTR)`
  - 带真实存盘路径 vs 全空字符串
* `swFm`（132 项）里**没有** split 定义 id → 也无法走 `CreateDefinition` 路线

草图延伸（`sw_sketch_extend`）：

* `SketchExtend(X, Y, Z)` 的 3 个参数是**目标点坐标**，不是"选线段"
* 无论选线段还是选端点，都返回 **False**，线段长度 10 → 10 mm 不变

    python tests/split_extend_check.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.core.com import none_dispatch, pyw, val        # noqa: E402
from swkit.verified import features as F                   # noqa: E402
from swkit.verified import inspect as I                    # noqa: E402
from swkit.verified import sketch_edit as SE               # noqa: E402
from swkit.verified import sketch_ops as S                 # noqa: E402
from swkit.verified._common import bodies                  # noqa: E402


def _split_probe(app):
    app.CloseAllDocuments(True)
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, -20, -12.5, 20, 12.5)
    F.extrude(doc, 20.0)
    d = pyw().Dispatch(app.ActiveDoc)
    before = len(bodies(d, 0))
    d.Extension.SelectByID2("上视基准面", "PLANE", 0, 0, 0, True, 0, none_dispatch(), 0)
    pre = val(d.FeatureManager, "PreSplitBody2")
    n_bodies = len(list(pre)) if pre is not None else 0
    d.ClearSelection2(True)
    results = []
    for consume in (True, False):
        feat = d.FeatureManager.PostSplitBody2(list(pre), consume,
                                               [None] * n_bodies, [""] * n_bodies, "")
        results.append(feat is not None)
    after = len(bodies(pyw().Dispatch(app.ActiveDoc), 0))
    return {"pre_split_bodies": n_bodies, "post_split_created": results,
            "solids_before": before, "solids_after": after}


def _extend_probe(app):
    app.CloseAllDocuments(True)
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.line(doc, 0.0, 0.0, 10.0, 0.0)
    d = pyw().Dispatch(app.ActiveDoc)
    before = SE.seg_stats(d)[1]
    sk = d.SketchManager.ActiveSketch
    segs = list(val(sk, "GetSketchSegments") or [])
    d.ClearSelection2(True)
    ret = None
    if segs:
        segs[0].Select2(False, 0)
        ret = d.SketchManager.SketchExtend(0.020, 0.0, 0.0)
    after = SE.seg_stats(d)[1]
    return {"returned": ret, "length_before_mm": round(before, 3),
            "length_after_mm": round(after, 3)}


def main() -> int:
    app = pyw().Dispatch("SldWorks.Application")
    split = _split_probe(app)
    extend = _extend_probe(app)
    print("split :", json.dumps(split, ensure_ascii=False))
    print("extend:", json.dumps(extend, ensure_ascii=False))

    checks = {
        "pre_split_computes_two": split["pre_split_bodies"] == 2,
        "post_split_never_creates": not any(split["post_split_created"]),
        "split_geometry_unchanged": split["solids_before"] == split["solids_after"],
        "extend_returns_false": extend["returned"] is False,
        "extend_length_unchanged": abs(extend["length_after_mm"]
                                       - extend["length_before_mm"]) < 1e-6,
    }
    print("checks:", checks)
    ok = all(checks.values())
    print("\n合计 1 项，通过 %d（结论：两条都调不通，已固化）" % (1 if ok else 0))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
