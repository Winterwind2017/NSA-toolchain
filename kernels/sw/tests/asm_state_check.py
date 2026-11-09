"""tests/asm_state_check.py —— 装配结构/状态族 + 特征抑制 真机验收

覆盖：新建装配 / 插组件 / 装配树 / 抑制组件 / 隐藏组件 / 替换组件 /
特征的抑制与解除抑制。

    python tests/asm_state_check.py
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

from swkit.core.com import pyw                      # noqa: E402
from swkit.verified import asm_state as A           # noqa: E402

SIM = r"D:\bililive\acad_out\SW_ADV\sim"
P1 = os.path.join(SIM, "box_hole.SLDPRT")
P2 = os.path.join(SIM, "box_off.SLDPRT")


def main() -> int:
    app = pyw().Dispatch("SldWorks.Application")
    app.CloseAllDocuments(True)
    results = {}

    # 顺序很重要：先建装配（它会 CloseAllDocuments），再打开零件，
    # 插入组件时由 `_activate` 把装配切回活动文档。
    results["create_assembly"] = A.create_assembly()
    if not results["create_assembly"].get("ok"):
        print(json.dumps(results["create_assembly"], ensure_ascii=False, default=str)[:300])
        return 2
    asm = pyw().Dispatch(app.ActiveDoc)

    for p in (P1, P2):
        if app.OpenDoc(p, 1) is None:
            print("打不开：%s" % p)
            return 2

    results["insert_1"] = A.insert_component(asm, P1, 0, 0, 0)
    results["insert_2"] = A.insert_component(asm, P2, 120, 0, 0)
    results["assembly_tree"] = A.assembly_tree(asm)

    names = [c.get("name") for c in
             (results["assembly_tree"].get("detail") or {}).get("components", [])]
    target = names[0] if names else ""
    results["suppress_on"] = A.suppress_component(asm, target, suppress=True)
    results["suppress_off"] = A.suppress_component(asm, target, suppress=False)
    results["hide_on"] = A.hide_component(asm, target, hide=True)
    results["hide_off"] = A.hide_component(asm, target, hide=False)
    results["replace"] = A.replace_component(asm, target, P2)

    # 特征抑制：在零件上做（找最后一个切除特征）
    if app.OpenDoc(P1, 1) is not None:
        try:
            app.ActivateDoc("box_hole")
        except Exception:
            pass
        part = pyw().Dispatch(app.ActiveDoc)
        print("   特征抑制用文档 =", part.GetTitle)
        feat_name = None
        f = part.FirstFeature
        guard = 0
        while f is not None and guard < 100:
            guard += 1
            fw = pyw().Dispatch(f)
            try:
                if str(fw.GetTypeName2) in ("ICE", "Cut", "CutFeature"):
                    feat_name = fw.Name
            except Exception:
                pass
            f = fw.GetNextFeature
        if feat_name:
            results["suppress_feature"] = A.suppress_feature(part, feat_name)
            results["unsuppress_feature"] = A.unsuppress_feature(part, feat_name)
        else:
            results["feature"] = {"ok": None, "skipped": "没有切除特征"}

    for name, res in results.items():
        if res.get("ok") is None:
            print("-- %-20s SKIP  %s" % (name, res.get("skipped")))
            continue
        print("== %-20s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("type", "title", "part", "components_before",
                         "components_after", "count", "component", "before", "after",
                         "target", "before_hidden", "after_hidden", "before_path",
                         "after_path", "feature", "error", "note")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:320])

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
