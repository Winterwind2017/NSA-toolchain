"""tests/balloon_check.py —— 球标（BOM 序号）真机验收

球标依赖 BOM 项号，所以夹具必须是**装配图**：

1. 建一个两组件装配并另存（球标要能重新打开）；
2. 从该装配建图纸 + 等轴测视图；
3. `balloon()` 内部先 `InsertBomTable2`（7 参），再 `AutoBalloon2(1, True)`；
4. 判据：BOM 存在 **且** 气球数 > 0（或视图注释数增加）。

    python tests/balloon_check.py
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
from swkit.verified import drawing as D               # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"
P1 = os.path.join(SIM, "box_hole.SLDPRT")
P2 = os.path.join(SIM, "box_off.SLDPRT")
ASM_TPL = (r"C:\ProgramData\SolidWorks\SOLIDWORKS 2025\templates"
           r"\gb_assembly.asmdot")
ASM_OUT = os.path.join(SIM, "check_balloon.SLDASM")


def build_assembly() -> str:
    from swkit.core.com import comtypes_bundle
    tlb = os.environ.get("SW_TLB") or \
        r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"
    sw, app_ct = comtypes_bundle(tlb)

    app_w = pyw().Dispatch("SldWorks.Application")
    app_w.CloseAllDocuments(True)
    for part in (P1, P2):
        if app_w.OpenDoc(part, 1) is None:
            raise RuntimeError("打不开：%s" % part)
    if app_w.NewDocument(ASM_TPL, 0, 0.0, 0.0) is None:
        raise RuntimeError("新建装配失败")
    asm_ct = app_ct.ActiveDoc.QueryInterface(sw.IAssemblyDoc)
    for i, part in enumerate((P1, P2)):
        asm_ct.AddComponent5(part, 0, "", False, "", 0.12 * i, 0.0, 0.0)
    asm_w = pyw().Dispatch(app_w.ActiveDoc)
    if os.path.exists(ASM_OUT):
        try:
            os.remove(ASM_OUT)
        except OSError:
            pass
    asm_w.SaveAs3(ASM_OUT, 0, 2)
    return ASM_OUT


def main() -> int:
    app = pyw().Dispatch("SldWorks.Application")
    asm = build_assembly()
    print("装配已存：%s（%d B）" % (asm, os.path.getsize(asm) if os.path.exists(asm) else -1))

    fx = D.new_drawing(asm, view="isometric")
    print("夹具：ok=%s views=%s" % (fx.get("ok"), (fx.get("detail") or {}).get("views")))
    if not fx.get("ok"):
        print(json.dumps(fx, ensure_ascii=False, default=str)[:400])
        return 2

    doc = pyw().Dispatch(app.ActiveDoc)
    res = D.balloon(doc)
    print("balloon ok=%s checks=%s" % (res.get("ok"), res.get("checks")))
    print(json.dumps(res.get("detail") or {}, ensure_ascii=False, default=str)[:600])
    return 0 if res.get("ok") else 4


if __name__ == "__main__":
    raise SystemExit(main())
