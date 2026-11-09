"""tests/inspect_check.py —— 只读检查族真机验收

覆盖：状态/打开文档/模型信息/特征表/质量属性/实体计数/自定义属性(读+写)/
材料(读+写)/重建/尺寸(读+改)/显示模式/显示状态。

判据都是**读数**：体积为正、属性写后读回相等、材料读回含目标名、尺寸读回等于目标、
显示模式读回等于目标值。

    python tests/inspect_check.py [--part box_hole.SLDPRT]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.core.com import pyw, val              # noqa: E402
from swkit.verified import inspect as I          # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default=os.path.join(SIM, "box_hole.SLDPRT"))
    args = ap.parse_args()
    app = pyw().Dispatch("SldWorks.Application")

    # 必须先关文档再复制：上一次运行留下的文档会锁住目标文件
    # （WinError 32 另一个程序正在使用此文件）
    app.CloseAllDocuments(True)
    dst = os.path.join(SIM, "check_inspect.SLDPRT")
    if os.path.exists(dst):
        try:
            os.remove(dst)
        except OSError as exc:
            print("删不掉旧副本：%s" % exc)
            return 2
    shutil.copy2(args.part, dst)
    if app.OpenDoc(dst, 1) is None:
        print("打不开：%s" % dst)
        return 2
    doc = pyw().Dispatch(app.ActiveDoc)

    results = {}
    results["status"] = I.status()
    results["open_documents"] = I.open_documents()
    results["model_info"] = I.model_info(doc)
    results["features"] = I.features(doc)
    results["mass_properties"] = I.mass_properties(doc)
    results["bodies"] = I.bodies(doc)
    results["custom_properties"] = I.custom_properties(doc)
    results["set_custom_property"] = I.set_custom_property(doc, "swkit_tag", "r8-check")
    results["custom_after_set"] = I.custom_properties(doc)
    results["material"] = I.material(doc)
    results["set_material"] = I.set_material(doc, "AISI 304")
    results["material_after"] = I.material(doc)
    results["rebuild"] = I.rebuild(doc)
    results["display_mode"] = I.display_mode(doc, "shaded")
    results["display_states"] = I.display_states(doc)

    # 尺寸：从特征里找一个尺寸名（box_hole 的切除-拉伸深度）
    dim_name = None
    for feat in I._iter_features(doc):
        try:
            if val(feat, "GetTypeName2") in ("ICE", "Cut", "CutFeature"):
                dims = val(feat, "GetFirstDisplayDimension")
                d = dims
                guard = 0
                while d is not None and guard < 12:
                    guard += 1
                    dim = val(pyw().Dispatch(d), "GetDimension")
                    if dim is not None:
                        dim_name = val(dim, "FullName")
                        break
                    d = val(pyw().Dispatch(d), "GetNext3")
        except Exception:
            continue
        if dim_name:
            break
    if dim_name:
        results["get_dimension"] = I.get_dimension(doc, dim_name)
        cur = (results["get_dimension"].get("detail") or {}).get("value_mm")
        if isinstance(cur, float):
            target = round(cur + 1.0, 3)
            results["set_dimension"] = I.set_dimension(doc, dim_name, target)
            results["restore_dimension"] = I.set_dimension(doc, dim_name, cur)
    else:
        results["dimension"] = {"ok": None, "skipped": "没找到可用尺寸名"}

    for name, res in results.items():
        if res.get("ok") is None:
            print("-- %-20s SKIP  %s" % (name, res.get("skipped")))
            continue
        print("== %-20s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("revision", "document_count", "count", "title", "type",
                         "features", "bodies", "volume_m3", "mass_kg", "solids",
                         "surfaces", "properties", "readback", "written",
                         "material_user", "requested", "value_mm", "target_mm",
                         "after_mm", "before", "after", "mode_name", "names",
                         "features_before", "features_after", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:340])

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
