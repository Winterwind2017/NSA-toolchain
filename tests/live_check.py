"""tests/live_check.py —— 真机验收（不是单测，是要连 SolidWorks 的）

流程：
  1) 关闭所有文档 → 打开两个测试零件 → 用装配模板新建装配
  2) 用 comtypes 的 `AddComponent5`（8 参）插入组件
  3) 调 `swkit.pattern_component(linear, count=3)` → 断言组件增加、出现阵列实例
  4) 重建 → 调 `swkit.mirror_components()` → 断言组件增加、出现镜像件
  5) 把两条证据字典打成 JSON 打印

用法：
    python tests/live_check.py [--p1 零件1] [--p2 零件2] [--template 装配模板]

依赖：pywin32、comtypes（comtypes 也可用 `SWKIT_VENDOR` 指向一个 vendor 目录）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor):
    sys.path.insert(0, _vendor)

from swkit.core.com import pyw                     # noqa: E402
from swkit.verified.assembly import (              # noqa: E402
    component_names, mirror_components, pattern_component,
)

DEFAULT_P1 = r"D:\bililive\acad_out\SW_ADV\sim\box_hole.SLDPRT"
DEFAULT_P2 = r"D:\bililive\acad_out\SW_ADV\sim\box_off.SLDPRT"
DEFAULT_TPL = (r"C:\ProgramData\SolidWorks\SOLIDWORKS 2025\templates"
               r"\gb_assembly.asmdot")


def build_assembly(p1: str, p2: str, template: str, dx: float = 0.12):
    """建一个两组件装配，返回 pywin32 的装配文档对象。"""
    from comtypes.client import CreateObject, GetModule

    tlb = os.environ.get("SW_TLB") or \
        r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"
    sw = GetModule(tlb)
    app_ct = CreateObject(sw.SldWorks)
    app_w = pyw().Dispatch("SldWorks.Application")

    app_w.CloseAllDocuments(True)
    for part in (p1, p2):
        if app_w.OpenDoc(part, 1) is None:
            raise RuntimeError("打不开零件：%s" % part)
    if app_w.NewDocument(template, 0, 0.0, 0.0) is None:
        raise RuntimeError("新建装配失败：%s" % template)

    asm_ct = app_ct.ActiveDoc.QueryInterface(sw.IAssemblyDoc)
    ok = 0
    for i, part in enumerate((p1, p2)):
        comp = asm_ct.AddComponent5(part, 0, "", False, "", dx * i, 0.0, 0.0)
        if comp is not None:
            ok += 1
    if ok < 2:
        raise RuntimeError("只插入了 %d 个组件（AddComponent5 需零件已打开 + 8 参）" % ok)

    return pyw().Dispatch(app_w.ActiveDoc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p1", default=DEFAULT_P1)
    ap.add_argument("--p2", default=DEFAULT_P2)
    ap.add_argument("--template", default=DEFAULT_TPL)
    ap.add_argument("--count", type=int, default=3)
    args = ap.parse_args()

    results = {}

    try:
        doc = build_assembly(args.p1, args.p2, args.template)
        results["fixture"] = {"ok": True, "components": len(component_names(doc)),
                              "names": component_names(doc)}
        results["pattern_linear"] = pattern_component(
            doc, kind="linear", count=args.count, spacing=0.05)
        results["pattern_linear"]["component_names_after"] = component_names(doc)
    except Exception as exc:                       # noqa: BLE001
        results["pattern_linear"] = {"ok": False,
                                     "error": "%s: %s" % (type(exc).__name__, exc)}

    try:
        doc = build_assembly(args.p1, args.p2, args.template)
        results["mirror"] = mirror_components(doc, plane_name="前视基准面")
        results["mirror"]["component_names_after"] = component_names(doc)
    except Exception as exc:                       # noqa: BLE001
        results["mirror"] = {"ok": False,
                             "error": "%s: %s" % (type(exc).__name__, exc)}

    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    ok = results.get("pattern_linear", {}).get("ok") and results.get("mirror", {}).get("ok")
    print("\n判定：%s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
