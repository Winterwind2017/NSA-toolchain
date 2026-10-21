"""真机用例：四族判据（geom / dim / export / block-table）+ 每例前后环境自检。

跑法（需要本机 AutoCAD 2025；未运行会自动用 `/p "<<VANILLA>>"` 起一个）：

    python tests/live_judges.py                # 跑全部
    python tests/live_judges.py --only geom    # 只跑一个族
    python tests/live_judges.py --keep         # 跑完不退出 AutoCAD（调试用）

产出：
    _scratch/judges_<时间戳>/results.json      完整证据（每例 checks/detail/raw）
    _scratch/judges_<时间戳>/*.dwg|dxf|pdf     每个用例的落盘文件

判据本身在 `src/acadkit/judges/`；这里只负责"造图 → 存盘 → 重开 → 判"。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import pythoncom                                            # noqa: E402
import win32com.client as w                                 # noqa: E402

from acadkit.core import com, env, launch, plot as plotmod  # noqa: E402
from acadkit.judges import block_table as bt                # noqa: E402
from acadkit.judges import dim, export, geom                # noqa: E402
from acadkit.judges.case import Case, CaseRunner, finish, env_signature  # noqa: E402

VT_ARRAY, VT_R8 = pythoncom.VT_ARRAY, pythoncom.VT_R8


def pt(x: float, y: float, z: float = 0.0):
    return w.VARIANT(VT_ARRAY | VT_R8, (float(x), float(y), float(z)))


def dbl(vals):
    return w.VARIANT(VT_ARRAY | VT_R8, [float(v) for v in vals])


def ms_of(doc):
    """取 ModelSpace：AutoCAD 正忙时会拒收呼叫，必须重试（不是"没有这个属性"）。"""
    return com.retry(lambda: doc.ModelSpace, label="ModelSpace")


# ── geom ────────────────────────────────────────────────────────────
def build_circle(doc, ctx):
    ms = ms_of(doc)
    com.retry(lambda: ms.AddCircle(pt(10, 20, 0), 25.0), label="AddCircle")


def build_line(doc, ctx):
    ms = ms_of(doc)
    com.retry(lambda: ms.AddLine(pt(0, 0, 0), pt(60, 0, 0)), label="AddLine")


def build_rect(doc, ctx):
    ms = ms_of(doc)
    pl = com.retry(lambda: ms.AddLightWeightPolyline(
        dbl([0, 0, 40, 0, 40, 30, 0, 30])), label="AddLightWeightPolyline")
    pl.Closed = True


# ── dim ─────────────────────────────────────────────────────────────
def build_linear(doc, ctx):
    ms = ms_of(doc)
    com.retry(lambda: ms.AddLine(pt(0, 0, 0), pt(60, 0, 0)), label="AddLine")
    com.retry(lambda: ms.AddDimRotated(pt(0, 0, 0), pt(60, 0, 0),
                                       pt(30, 10, 0), 0.0), label="AddDimRotated")


def build_diametric(doc, ctx):
    ms = ms_of(doc)
    com.retry(lambda: ms.AddCircle(pt(10, 20, 0), 25.0), label="AddCircle")
    com.retry(lambda: ms.AddDimDiametric(pt(35, 20, 0), pt(-15, 20, 0), 8.0),
              label="AddDimDiametric")


def build_radial(doc, ctx):
    ms = ms_of(doc)
    com.retry(lambda: ms.AddCircle(pt(10, 20, 0), 25.0), label="AddCircle")
    com.retry(lambda: ms.AddDimRadial(pt(10, 20, 0), pt(35, 20, 0), 8.0),
              label="AddDimRadial")


def build_missing_api(doc, ctx):
    """负例：AddDimLinear 在本机不存在，调用必须抛错。"""
    ms = ms_of(doc)
    try:
        ms.AddDimLinear(pt(0, 0, 0), pt(60, 0, 0), pt(30, -10, 0))
        ctx["artifacts"]["raised"] = None
        ctx["notes"].append("AddDimLinear 竟然调用成功——负例前提不成立")
    except Exception as exc:                            # noqa: BLE001
        ctx["artifacts"]["raised"] = type(exc).__name__
        ctx["notes"].append("AddDimLinear -> %s" % type(exc).__name__)


# ── export ──────────────────────────────────────────────────────────
def _basic_drawing(doc):
    ms = ms_of(doc)
    com.retry(lambda: ms.AddCircle(pt(10, 10, 0), 25.0), label="AddCircle")
    com.retry(lambda: ms.AddLine(pt(0, 0, 0), pt(60, 0, 0)), label="AddLine")
    return ms


def build_dwg(doc, ctx):
    _basic_drawing(doc)


def build_dxf(doc, ctx):
    _basic_drawing(doc)
    path = os.path.join(ctx["workdir"], "export_dxf.dxf")
    info = plotmod.save_as(doc, path, fmt=65)
    ctx["artifacts"]["dxf_path"] = path
    ctx["artifacts"]["dxf_save"] = info
    if not info["ok"]:
        ctx["notes"].append("DXF 落盘失败：%r" % (info,))


def build_pdf(doc, ctx):
    ms = _basic_drawing(doc)
    pl = com.retry(lambda: ms.AddLightWeightPolyline(
        dbl([0, 0, 40, 0, 40, 30, 0, 30])), label="AddLightWeightPolyline")
    pl.Closed = True
    com.retry(lambda: ms.AddText("ACADKIT JUDGE", pt(0, 40, 0), 5.0), label="AddText")
    path = os.path.join(ctx["workdir"], "export_pdf.pdf")
    info = plotmod.plot_model_to_pdf(doc, path)
    ctx["artifacts"]["pdf_path"] = path
    ctx["artifacts"]["plot"] = info


# ── block / table ───────────────────────────────────────────────────
def _define_block(doc, name="BOM_MARK"):
    blocks = doc.Blocks
    blk = com.retry(lambda: blocks.Add(pt(0, 0, 0), name), label="Blocks.Add")
    com.retry(lambda: blk.AddCircle(pt(0, 0, 0), 5.0), label="block.AddCircle")
    com.retry(lambda: blk.AddAttribute(2.5, 0, "Part No.", pt(-5, 6, 0),
                                       "PART_NO", "P-001"), label="AddAttribute")
    com.retry(lambda: blk.AddAttribute(2.5, 0, "Material", pt(-5, -8, 0),
                                       "MATERIAL", "Q235"), label="AddAttribute")
    return blk


def build_block_define(doc, ctx):
    _define_block(doc)


def _insert_block(doc, values: Dict[str, str]):
    ms = ms_of(doc)
    ref = com.retry(lambda: ms.InsertBlock(pt(100, 0, 0), "BOM_MARK",
                                           1.0, 1.0, 1.0, 0.0),
                    label="InsertBlock")
    for at in ref.GetAttributes():
        tag = str(at.TagString)
        if tag in values:
            at.TextString = values[tag]
    return ref


def build_block_insert(doc, ctx):
    _define_block(doc)
    _insert_block(doc, {"PART_NO": "P-777", "MATERIAL": "45#"})


def build_block_short(doc, ctx):
    """负例：插入后删掉一个属性，属性个数应当判不过。"""
    _define_block(doc)
    ref = _insert_block(doc, {"PART_NO": "P-777"})
    removed = None
    for at in ref.GetAttributes():
        if str(at.TagString) == "MATERIAL":
            try:
                at.Delete()
                removed = "MATERIAL"
            except Exception as exc:                    # noqa: BLE001
                ctx["notes"].append("删属性失败：%s: %s" % (type(exc).__name__, exc))
    ctx["artifacts"]["removed"] = removed
    if removed is None:
        ctx["notes"].append("没能删掉属性——负例退化为'值不对'")


def build_table(doc, ctx):
    """BOM 表：标题行 + 表头行 + 2 行明细 + 合计。

    本机实测（2026-10-21）：ACDBTABLE 的第 0 行是**合并的标题行**，往它的
    第 1..n 列 `SetText` 内存里读得到，但落盘重开后是空的。所以表头放在第 1 行，
    第 0 行只写标题——这也是真正 BOM 的排法。
    """
    ms = ms_of(doc)
    tbl = com.retry(lambda: ms.AddTable(pt(0, -60, 0), 5, 3, 8.0, 40.0),
                    label="AddTable")
    for key, v in BOM_CELLS.items():
        r, c = (int(x) for x in key.split(","))
        try:
            tbl.SetText(r, c, v)
        except Exception as exc:                        # noqa: BLE001
            ctx["notes"].append("SetText(%d,%d) 失败：%s" % (r, c, exc))


BOM_CELLS = {"0,0": "BOM",
             "1,0": "NO.", "1,1": "NAME", "1,2": "QTY",
             "2,0": "1", "2,1": "BRACKET", "2,2": "2",
             "3,0": "2", "3,1": "PLATE", "3,2": "3",
             "4,0": "TOTAL", "4,2": "5"}


# ── 用例清单 ────────────────────────────────────────────────────────
def cases() -> List[Case]:
    return [
        Case("geom.circle", "geom", "圆：L1–L4",
             build_circle,
             lambda rb, ctx: geom.judge_circle(rb, center=(10, 20, 0), radius=25.0)),
        Case("geom.line", "geom", "直线：L1–L4",
             build_line,
             lambda rb, ctx: geom.judge_line(rb, start=(0, 0, 0), end=(60, 0, 0))),
        Case("geom.rect", "geom", "矩形（闭合多段线）：L1–L4",
             build_rect,
             lambda rb, ctx: geom.judge_rect(rb, corner1=(0, 0), corner2=(40, 30))),

        Case("dim.linear", "dim", "线性标注：L1–L4",
             build_linear,
             lambda rb, ctx: dim.judge_linear(rb, p1=(0, 0), p2=(60, 0),
                                              dim_line=(30, 10), expected=60.0)),
        Case("dim.diametric", "dim", "直径标注：L1–L4",
             build_diametric,
             lambda rb, ctx: dim.judge_diametric(rb, radius=25.0)),
        Case("dim.radial", "dim", "半径标注：L1–L4",
             build_radial,
             lambda rb, ctx: dim.judge_radial(rb, radius=25.0)),
        Case("dim.api_missing", "dim", "负例：AddDimLinear 不存在（调用必须抛错）",
             build_missing_api,
             lambda rb, ctx: dim.judge_raised(ctx["artifacts"].get("raised"),
                                              expected=("AttributeError",)),
             is_negative=True, wants_reopen=False),

        Case("export.dwg", "export", "DWG：文件+魔数+重开一致",
             build_dwg,
             lambda rb, ctx: export.judge_dwg(rb,
                                              path=ctx["artifacts"]["dwg_path"],
                                              since=ctx["started"])),
        Case("export.dxf", "export", "DXF：段+族计数+重新导入",
             build_dxf,
             lambda rb, ctx: export.judge_dxf(rb,
                                              path=ctx["artifacts"]["dxf_path"],
                                              since=ctx["started"],
                                              dxf=ctx["artifacts"].get("dxf_info")),
             wants_dxf=True),
        Case("export.pdf", "export", "PDF：A3+非空白",
             build_pdf,
             lambda rb, ctx: export.judge_pdf(rb,
                                              path=ctx["artifacts"]["pdf_path"],
                                              since=ctx["started"],
                                              plot=ctx["artifacts"].get("plot"))),

        Case("block.define", "block-table", "块定义+属性定义：L1–L4",
             build_block_define,
             lambda rb, ctx: bt.judge_block_define(
                 rb, block_name="BOM_MARK",
                 attdefs={"PART_NO": "P-001", "MATERIAL": "Q235"},
                 entity_types={"CIRCLE": 1, "ATTRIBUTEDEFINITION": 2})),
        Case("block.insert_with_attributes", "block-table",
             "块插入+属性值：L1–L4",
             build_block_insert,
             lambda rb, ctx: bt.judge_block_insert(
                 rb, block_name="BOM_MARK",
                 attrs={"PART_NO": "P-777", "MATERIAL": "45#"},
                 insertion=(100, 0, 0))),
        Case("block.short_attributes", "block-table",
             "负例：属性少一个 → 判据必须失败",
             build_block_short,
             lambda rb, ctx: bt.judge_block_insert(
                 rb, block_name="BOM_MARK",
                 attrs={"PART_NO": "P-777", "MATERIAL": "Q235"},
                 insertion=(100, 0, 0)),
             expect="fail", expect_fail_checks=("attr_count",)),
        Case("table.bom", "block-table", "BOM 表：逐格+合计：L1–L4",
             build_table,
             lambda rb, ctx: bt.judge_table(rb, rows=5, cols=3,
                                            cells=BOM_CELLS, sum_column=2,
                                            detail_rows=(2, 3), total_row=4)),
    ]


# ── 输出 ────────────────────────────────────────────────────────────
MARK = {True: "PASS", False: "FAIL"}


def print_table(results: List[Dict[str, Any]]) -> None:
    from acadkit.judges import JUDGES

    print("")
    print("%-12s %-30s %-7s %-5s %-5s %-7s %s"
          % ("族", "用例", "级别", "类型", "结果", "耗时", "失败项"))
    print("-" * 112)
    for r in results:
        failed = [k for k, v in (r.get("checks") or {}).items() if v is False]
        level = (JUDGES.get(r["id"]) or {}).get("level", "-")
        print("%-12s %-30s %-7s %-5s %-5s %6.1fs %s"
              % (r["family"], r["id"], level,
                 "负例" if r["negative"] else "正常",
                 MARK[bool(r["ok"])], r.get("duration_s") or 0.0,
                 ", ".join(failed) if failed else "-"))
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    print("-" * 112)
    print("合计 %d 例：通过 %d / 失败 %d" % (total, passed, total - passed))
    env_total = sum(1 for r in results for k in (r.get("checks") or {})
                    if k.startswith("env_"))
    env_fail = [(r["id"], k) for r in results
                for k, v in (r.get("checks") or {}).items()
                if k.startswith("env_") and v is not True]
    print("环境自检：%d 例，共 %d 项检查，未通过 %d 项"
          % (total, env_total, len(env_fail)))
    for cid, key in env_fail:
        print("  - %s: %s" % (cid, key))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="acadkit 四族判据真机用例")
    ap.add_argument("--only", default=None,
                    help="只跑某个族或某个用例 id（逗号分隔）")
    ap.add_argument("--keep", action="store_true", help="跑完不退出 AutoCAD")
    ap.add_argument("--workdir", default=None)
    args = ap.parse_args(argv)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    workdir = args.workdir or os.path.join(ROOT, "_scratch", "judges_%s" % stamp)
    os.makedirs(workdir, exist_ok=True)

    all_cases = cases()
    if args.only:
        keys = [k.strip() for k in args.only.split(",") if k.strip()]
        all_cases = [c for c in all_cases
                     if c.id in keys or c.family in keys]
    if not all_cases:
        print("没有匹配的用例")
        return 2

    sig_before = env_signature()
    print("跑前环境指纹：%s" % sig_before)

    info = launch.launch()
    app = info["app"]
    launched = info["launched"]
    print("AutoCAD：%s（profile=%r，等待 %ss）"
          % ("本次启动" if launched else "附加到已运行实例",
             info.get("profile"), info.get("waited_s")))

    rc = 0
    results: List[Dict[str, Any]] = []
    runner = None
    baseline = None
    try:
        runner = CaseRunner(app, workdir, log=lambda m: print(m))
        baseline = runner.ensure_baseline_doc()
        app = com.attach_or_none() or app          # 取一次新代理再读 profile
        profile = launch.read_profile(app)
        print("活动文档 profile：%r" % (profile,))
        if profile is None or profile.strip() != env.REQUIRED_PROFILE:
            print("拒绝在非 %s 配置下跑用例（实际 %r）"
                  % (env.REQUIRED_PROFILE, profile))
            rc = 4
            return rc
        for case in all_cases:
            print("\n>>> %s  %s" % (case.id, case.title))
            res = runner.run(case)
            results.append(res)
            failed = [k for k, v in res["checks"].items() if v is False]
            print("    %s  %.1fs  %s"
                  % (MARK[bool(res["ok"])], res["duration_s"],
                     ("失败项：" + ", ".join(failed)) if failed else ""))
            if res.get("notes"):
                for note in res["notes"]:
                    print("    note: %s" % note)
    except Exception as exc:                            # noqa: BLE001
        print("!! 跑用例时异常退出：%s: %s" % (type(exc).__name__, exc))
        traceback.print_exc()
        rc = 1
    finally:
        try:
            if runner is not None and baseline is not None:
                fin = finish(app, baseline, quit_app=(launched and not args.keep))
                print("\n收尾：%s" % json.dumps(fin, ensure_ascii=False, default=str))
        except Exception as exc:                        # noqa: BLE001
            print("!! 收尾失败：%s: %s" % (type(exc).__name__, exc))
            rc = 1

    sig_after = env_signature()
    print("跑后环境指纹：%s" % sig_after)

    payload = {
        "tool": "acadkit live judges",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "workdir": workdir,
        "autoacd": {"launched": launched, "exe": info.get("exe"),
                    "profile": info.get("profile"),
                    "waited_s": info.get("waited_s")},
        "env_before": sig_before,
        "env_after": sig_after,
        "results": results,
    }
    out = os.path.join(workdir, "results.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    print("\n证据：%s" % out)

    print_table(results)

    env_bad = []
    if sig_after["sv_count"] > sig_before["sv_count"]:
        env_bad.append(".sv$ 增加了 %d 个" % (sig_after["sv_count"]
                                              - sig_before["sv_count"]))
    if launched and not args.keep and sig_after["process_count"] != 0:
        env_bad.append("AutoCAD 没退出（进程 %d）" % sig_after["process_count"])
    if env_bad:
        print("环境收尾不合格：%s" % "; ".join(env_bad))
        rc = rc or 1

    if results and not all(r["ok"] for r in results):
        rc = rc or 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
