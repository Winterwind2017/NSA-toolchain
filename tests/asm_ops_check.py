"""tests/asm_ops_check.py —— 装配侧其余能力真机验收（含干涉检查 A/B）

A/B 设计（这是干涉检查唯一有意义的验证方式）：

* **重叠**：两个 100 mm 宽零件，第二件 X 偏移 0.05 m → 干涉数应 ≥ 1
* **分开**：偏移 0.12 m → 干涉数应为 0

另外验证固定组件、显示全部、自动爆炸。

    python tests/asm_ops_check.py
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

from swkit.core.com import pyw                        # noqa: E402
from swkit.verified import asm_ops as A               # noqa: E402

P1 = r"D:\bililive\acad_out\SW_ADV\sim\box_hole.SLDPRT"
P2 = r"D:\bililive\acad_out\SW_ADV\sim\box_off.SLDPRT"
TPL = (r"C:\ProgramData\SolidWorks\SOLIDWORKS 2025\templates"
       r"\gb_assembly.asmdot")


def build(dx: float):
    from comtypes.client import CreateObject, GetModule
    tlb = os.environ.get("SW_TLB") or \
        r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"
    sw = GetModule(tlb)
    app_ct = CreateObject(sw.SldWorks)
    app_w = pyw().Dispatch("SldWorks.Application")
    app_w.CloseAllDocuments(True)
    for part in (P1, P2):
        if app_w.OpenDoc(part, 1) is None:
            raise RuntimeError("打不开：%s" % part)
    if app_w.NewDocument(TPL, 0, 0.0, 0.0) is None:
        raise RuntimeError("新建装配失败")
    asm_ct = app_ct.ActiveDoc.QueryInterface(sw.IAssemblyDoc)
    for i, part in enumerate((P1, P2)):
        asm_ct.AddComponent5(part, 0, "", False, "", dx * i, 0.0, 0.0)
    return pyw().Dispatch(app_w.ActiveDoc)


def main() -> int:
    results = {}

    doc = build(0.12)                                  # 分开
    results["interference_separated"] = A.check_interference(doc)

    doc = build(0.05)                                  # 重叠
    results["interference_overlapping"] = A.check_interference(doc)

    doc = build(0.12)
    results["fix_component"] = A.fix_component(doc)

    doc = build(0.12)
    results["show_all_components"] = A.show_all_components(doc)

    doc = build(0.12)
    results["explode_assembly"] = A.explode_assembly(doc)

    for name, res in results.items():
        print("== %-26s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("count", "verdict", "is_fixed", "components",
                         "views_before", "views_after", "is_hidden", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:400])

    # A/B 语义：分开必须 0，重叠必须 >0
    sep = (results["interference_separated"].get("detail") or {}).get("count")
    ovl = (results["interference_overlapping"].get("detail") or {}).get("count")
    ab_ok = (sep == 0) and (ovl is not None and ovl > 0)
    print("\n干涉 A/B：分开=%s 重叠=%s → %s" % (sep, ovl, "PASS" if ab_ok else "FAIL"))

    others = [k for k in results if not k.startswith("interference_")]
    passed = sum(1 for k in others if results[k].get("ok"))
    print("其余 %d 项，通过 %d" % (len(others), passed))
    return 0 if (ab_ok and passed == len(others)) else 4


if __name__ == "__main__":
    raise SystemExit(main())
