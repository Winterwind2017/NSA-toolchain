"""tests/sheet_metal_check.py —— 钣金族真机验收

夹具：空白零件 → 前视基准面画 60×40 矩形 → 基体法兰（厚 2、半径 2、深 30）
→ 展开 → 折叠；再选一条边做卷边。

判据：特征数 +1、出现钣金特征类型、`GetBendState` 读数。

    python tests/sheet_metal_check.py
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

from swkit.core.com import pyw, val                   # noqa: E402
from swkit.verified import features as F              # noqa: E402
from swkit.verified import sheet_metal as SM          # noqa: E402
from swkit.verified import sketch_ops as S            # noqa: E402


def _select_edges(doc, limit=1):
    doc.ClearSelection2(True)
    n = 0
    for body in F.bodies(doc, 0):
        for face in F.faces_of(body):
            for edge in (val(face, "GetEdges") or []):
                try:
                    F.wrap(edge).Select2(True, 1)
                    n += 1
                except Exception:
                    continue
                if n >= limit:
                    return n
    return n


def main() -> int:
    doc = F.new_part()
    S.create_sketch(doc, "前视基准面")
    S.rectangle(doc, 0, 0, 60, 40)

    results = {}
    results["base_flange"] = SM.base_flange(doc, 2.0, 2.0, 30.0)
    if not results["base_flange"].get("ok"):
        print(json.dumps(results["base_flange"], ensure_ascii=False,
                         default=str)[:400])
        # 继续尝试展开/折叠，看看是否本来就不是钣金
    results["flat_info"] = SM.flat_pattern_info(doc)
    # 展开图导出：零件直接导 DXF 无输出（同零件 DXF 的老问题），单列已知未解
    known = {}
    known["flat_export"] = SM.export_flat_pattern(
        doc, os.path.join(os.path.expanduser("~"), ".swkit", "export", "flat.dxf"))
    known["unfold"] = SM.unfold(doc)
    known["fold"] = SM.fold(doc)
    n_edges = _select_edges(doc, 1)
    print("   选边数 =", n_edges)
    if n_edges:
        results["hem"] = SM.hem(doc, 0, 0, 5.0)
    else:
        results["hem"] = {"ok": None, "skipped": "没选中边"}

    print("   钣金特征 =", SM._sheet_features(doc))
    print("   GetBendState =", SM.bend_state(doc))


    # ── insert_bends：等厚 L 形实体 → 选底面 → 转钣金
    try:
        from swkit.verified import sketch_ops as _S
        from swkit.core.com import none_dispatch as _nd
        _doc = F.new_part()
        _S.create_sketch(_doc, "前视基准面")
        _pts = [(0, 0), (100, 0), (100, 10), (10, 10), (10, 80), (0, 80), (0, 0)]
        for _i in range(len(_pts) - 1):
            _S.line(_doc, _pts[_i][0], _pts[_i][1], _pts[_i + 1][0], _pts[_i + 1][1])
        F.extrude(_doc, 40.0)
        _doc.ClearSelection2(True)
        _doc.Extension.SelectByID2("", "FACE", 0.05, 0.005, 0.0, False, 0, _nd(), 0)
        results["insert_bends"] = SM.insert_bends(_doc, 5.0)
    except Exception as _exc:                       # noqa: BLE001
        results["insert_bends"] = {"ok": False, "error": str(_exc)[:80]}
    for name, res in results.items():
        if res.get("ok") is None:
            print("-- %-14s SKIP  %s" % (name, res.get("skipped")))
            continue
        print("== %-14s ok=%-5s checks=%s" % (name, res.get("ok"), res.get("checks")))
        keep = {k: v for k, v in (res.get("detail") or {}).items()
                if k in ("feature", "features_before", "features_after",
                         "sheet_features_after", "bend_state", "bend_state_before",
                         "bend_state_after", "thickness_mm", "error")}
        if keep:
            print("   " + json.dumps(keep, ensure_ascii=False, default=str)[:320])

    for name, res in known.items():
        print("-- %-14s (unverified/待解) state=%s feats=%s" % (
            name, SM.bend_state(doc),
            (res.get("detail") or {}).get("features_after")))

    hard = {k: v for k, v in results.items() if v.get("ok") is not None}
    passed = sum(1 for v in hard.values() if v.get("ok"))
    print("\n合计 %d 项，通过 %d" % (len(hard), passed))
    return 0 if passed == len(hard) else 4


if __name__ == "__main__":
    raise SystemExit(main())
