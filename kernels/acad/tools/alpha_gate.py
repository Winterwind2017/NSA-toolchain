#!/usr/bin/env python3
"""Alpha 门禁：5 条**端到端工作流**真机跑一遍，产出 `docs/ALPHA_GATE.md`。

    python tools/alpha_gate.py                # 跑全部 5 条，写 docs/ALPHA_GATE.md
    python tools/alpha_gate.py --only W1,W4   # 只跑指定工作流
    python tools/alpha_gate.py --keep         # 跑完不退出 AutoCAD
    python tools/alpha_gate.py --no-write     # 只跑不写文档（调试用）

和 `tests/live_judges.py` 的区别：

    live_judges  按**能力**验（一条能力一个文档、建→读回→重开）
    alpha_gate   按**工作流**验（一个文档里串多步，最后一步是可交付产物：
                 PDF/DWG/DXF，并做重开一致性检查）

能力全过不等于工作流能跑通——中间的状态污染、图层/布局残留、出图设置串味，
只有串起来才暴露。这就是这道门禁的意义。

判据（每条工作流都查）：
    steps       所有步骤的能力 build 都无异常
    model       模型空间实体数 > 0
    artifact    导出文件存在且 ≥ 阈值（PDF ≥ 5KB，DWG/DXF ≥ 2KB）
    reopen      重开后实体数与原文档一致（±1，容忍布局视口差异）
    pages       PDF 页数符合预期（多页工作流域为 2）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import caps                                    # noqa: E402
from acadkit.core import com, env, launch, plot              # noqa: E402
from acadkit.judges.case import CaseRunner, env_signature    # noqa: E402

OUT = os.path.join(ROOT, "docs", "ALPHA_GATE.md")

# ── 5 条工作流 ────────────────────────────────────────────────────────
# steps 里的能力按顺序在**同一个文档**里执行；exports 决定产出什么、判什么。
WORKFLOWS: List[Dict[str, Any]] = [
    {
        "id": "W1",
        "name": "机械零件图直出",
        "story": "画外形 → 加线性/直径标注 → 粗糙度 + 形位公差 → 图框 → 出 PDF + DWG",
        "steps": ["geom.rect", "geom.circle", "geom.line", "dim.linear",
                  "dim.diametric", "symbol.roughness", "gdt.tolerance",
                  "frame.titleblock", "text.single"],
        "exports": ["pdf", "dwg"],
        "pages": 1,
    },
    {
        "id": "W2",
        "name": "BOM 与中文表格",
        "story": "BOM 表 → 中文表 → 说明文字 → 出 DXF 并重导比对",
        "steps": ["table.bom", "table.chinese", "text.single"],
        "exports": ["dxf"],
        "pages": 0,
    },
    {
        "id": "W3",
        "name": "装配图带序号",
        "story": "若干部件外形 → 序号气泡 → 中心线 + 中心标记 → 图框 → PDF",
        "steps": ["geom.rect", "geom.circle", "geom.polyline", "symbol.balloon",
                  "symbol.centerline", "symbol.centermark", "frame.titleblock"],
        "exports": ["pdf"],
        "pages": 1,
    },
    {
        "id": "W4",
        "name": "多布局出图",
        "story": "两个布局各放一张图 → 逐布局出 PDF → 合并成 2 页",
        "steps": ["layout.multipage", "export.pdf_multipage"],
        "exports": ["pdf_multipage"],
        "pages": 2,
        "model_min": 0,
        "check_layouts": 2,
    },
    {
        "id": "W5",
        "name": "电气 / PLC 专项",
        "story": "读 Electrical 元件库 → PLC 模块图 → P&ID 符号 → 出 DWG",
        "steps": ["ae.db", "plc.build", "pid.symbol"],
        "exports": ["dwg"],
        "pages": 0,
    },
]

MIN_BYTES = {"pdf": 5000, "pdf_multipage": 2000, "dwg": 2000, "dxf": 2000}

_WATCH = {"deadline": 0.0, "what": None, "workdir": None}


def start_watchdog(per_workflow_s: float, workdir: str) -> None:
    def loop() -> None:
        while True:
            time.sleep(1.0)
            if _WATCH["deadline"] and time.time() > _WATCH["deadline"]:
                msg = ("工作流 %s 超过 %.0fs 未返回 —— 大概率停在 AutoCAD 命令提示符上。"
                       "已强杀 acad.exe 并中止本轮。" % (_WATCH["what"], per_workflow_s))
                print("\n!! " + msg)
                sys.stdout.flush()
                try:
                    with open(os.path.join(workdir, "TIMEOUT.txt"), "w",
                              encoding="utf-8") as fh:
                        fh.write(msg + "\n")
                except Exception:                       # noqa: BLE001
                    pass
                subprocess.run(["taskkill", "/F", "/IM", "acad.exe"],
                               capture_output=True)
                os._exit(9)

    threading.Thread(target=loop, daemon=True).start()
    _WATCH["workdir"] = workdir


def pdf_pages(path: str) -> Optional[int]:
    """PDF 页数；没有可用的解析库时返回 None（不猜）。"""
    try:
        from pypdf import PdfReader
        return len(PdfReader(path).pages)
    except Exception:                                   # noqa: BLE001
        pass
    try:
        import fitz
        return fitz.open(path).page_count
    except Exception:                                   # noqa: BLE001
        return None


def run_cap(doc: Any, cap_id: str, workdir: str) -> Dict[str, Any]:
    cap = caps.get(cap_id)
    ctx: Dict[str, Any] = {
        "params": dict(cap.params), "artifacts": {}, "notes": [],
        "workdir": workdir, "started": time.time(),
    }
    cap.build(doc, ctx)
    return {"cap": cap_id, "artifacts": sorted(ctx["artifacts"]),
            "notes": ctx["notes"], "ctx": ctx}


def _warm_up(doc: Any) -> bool:
    """等 AutoCAD 把新文档的集合对象建好。

    实测（2026-11-18，alpha gate W2 偶发）：`Documents.Add()` 返回后立刻读
    `doc.TextStyles` / `ms.AddTable`，偶发拿到旧句柄 → `AttributeError: <unknown>.Add`。
    这里把常用集合都 touch 一遍，直到全部可读；读不到就退让重试，不抛异常
    （让真正的失败留在步骤里，便于定位）。
    """
    for _ in range(24):
        try:
            _ = int(doc.ModelSpace.Count)
            _ = int(doc.Layers.Count)
            _ = int(doc.TextStyles.Count)
            _ = int(doc.DimStyles.Count)
            _ = int(doc.Linetypes.Count)
            _ = int(doc.Layouts.Count)
            return True
        except Exception:                           # noqa: BLE001
            time.sleep(0.25)
    return False


def run_cap_safe(doc: Any, cap_id: str, workdir: str) -> Dict[str, Any]:
    """跑一个能力；只在"句柄失效且模型空间还是空的"时安全重试一次。

    为什么加条件：如果已经建出一部分实体再重试，会**重复建**，判据就假了。
    """
    for attempt in (1, 2):
        try:
            return run_cap(doc, cap_id, workdir)
        except Exception as exc:                    # noqa: BLE001
            empty = True
            try:
                empty = int(doc.ModelSpace.Count) == 0
            except Exception:                       # noqa: BLE001
                pass
            if attempt == 1 and "<unknown>" in str(exc) and empty:
                time.sleep(0.8)
                continue
            raise
    raise RuntimeError("unreachable")


def _export_with_retry(doc: Any, path: str, ext: str, attempts: int = 3) -> Dict[str, Any]:
    """导出一次不成就重试。

    实测：刚出完 PDF 立刻 `SaveAs` 到 .dwg，偶发落 0 字节（AutoCAD 还在收尾 plotting）。
    这里把"0 字节/未落盘"当成可重试的瞬时失败，退避后重来，最多 attempts 次。
    """
    info: Dict[str, Any] = {}
    for i in range(attempts):
        if ext == "pdf":
            info = plot.plot_model_to_pdf(doc, path)
        elif ext == "dxf":
            # 实测：SaveAs 只给 .dxf 扩展名落 0 字节，必须显式给格式码 65
            info = plot.save_as(doc, path, fmt=65)
        else:
            info = plot.save_as(doc, path)
        size = info.get("bytes") or (os.path.getsize(path) if os.path.exists(path) else 0)
        if info.get("ok") and size > 0:
            return info
        if i + 1 < attempts:
            time.sleep(0.8 * (i + 1))
    return info


def run_workflow(runner: CaseRunner, wf: Dict[str, Any], workdir: str) -> Dict[str, Any]:
    t0 = time.time()
    name = wf["id"]
    wdir = os.path.join(workdir, name)
    os.makedirs(wdir, exist_ok=True)
    checks: Dict[str, Any] = {}
    detail: Dict[str, Any] = {"id": name, "name": wf["name"], "story": wf["story"],
                              "steps": wf["steps"], "exports": wf["exports"],
                              "notes": [], "error": None}
    exports: List[Dict[str, Any]] = []
    count = None
    last_ctx: Dict[str, Any] = {"artifacts": {}}

    doc = runner.new_doc(name)
    _warm_up(doc)
    try:
        # 1) 串行跑步骤（同一个文档）
        for cap_id in wf["steps"]:
            out = run_cap_safe(doc, cap_id, wdir)
            detail["notes"] += out["notes"]
            last_ctx = out["ctx"]
        checks["steps"] = True
        detail["steps_run"] = list(wf["steps"])

        # 2) 模型空间实体数
        count = int(com.retry(lambda: doc.ModelSpace.Count, label="ModelSpace.Count"))
        detail["model_count"] = count
        checks["model"] = count >= int(wf.get("model_min", 1))

        want_layouts = wf.get("check_layouts")
        if want_layouts:
            names = []
            try:
                layouts = com.retry(lambda: doc.Layouts, label="Layouts")
                for i in range(int(layouts.Count)):
                    names.append(str(layouts.Item(i).Name))
            except Exception as exc:                # noqa: BLE001
                detail["notes"].append("读布局失败：%s" % exc)
            detail["layouts"] = names
            checks["layouts"] = len(names) >= int(want_layouts)

        # 3) 导出（此时文档还开着；重开校验放到关文档之后）
        for kind in sorted(wf["exports"], key=lambda k: 0 if k in ("dwg", "dxf") else 1):
            if kind == "pdf_multipage":
                mp = (last_ctx["artifacts"].get("multipage") or {})
                path = mp.get("path")
                size = os.path.getsize(path) if path and os.path.exists(path) else 0
                pages = pdf_pages(path) if path and os.path.exists(path) else None
                checks["artifact"] = bool(size >= MIN_BYTES[kind])
                checks["pages"] = pages == wf["pages"]
                exports.append({"kind": kind, "path": path, "bytes": size,
                                "ok": bool(mp.get("merge", {}).get("ok")),
                                "pages": pages})
                continue

            ext = {"pdf": "pdf", "dwg": "dwg", "dxf": "dxf"}[kind]
            path = os.path.join(wdir, "%s_%s.%s" % (name, kind, ext))
            info = _export_with_retry(doc, path, ext)
            size = info.get("bytes") or (os.path.getsize(path) if os.path.exists(path) else 0)
            checks["artifact"] = bool(info.get("ok") and size >= MIN_BYTES[kind])
            entry = {"kind": kind, "path": path, "bytes": size, "ok": bool(info.get("ok"))}
            if ext == "pdf":
                pages = pdf_pages(path)
                entry["pages"] = pages
                checks["pages"] = pages == wf["pages"]
            exports.append(entry)

    except Exception as exc:                            # noqa: BLE001
        detail["error"] = "%s: %s" % (type(exc).__name__, exc)
        detail["traceback"] = traceback.format_exc(limit=6)
    finally:
        # 先关文档：否则重开同一个路径会被 AutoCAD 拒绝（文件正在打开）
        try:
            runner._close(doc, "alpha:%s" % name)
        except Exception:                               # noqa: BLE001
            pass

    # 4) 重开一致性（文档已关，可以重新打开同一路径）
    detail["export_list"] = exports
    for entry in exports:
        if entry.get("kind") in ("dwg", "dxf") and count is not None and entry.get("bytes"):
            reopened, _close_s = runner._reopen(entry["path"], "alpha:" + name)
            rc = None if reopened is None else len(getattr(reopened, "entities", []) or [])
            entry["reopen_count"] = rc
            checks["reopen"] = (rc is not None and abs(int(rc) - count) <= 1)

    detail["checks"] = checks
    detail["ok"] = bool(checks) and all(bool(v) for v in checks.values()) and not detail["error"]
    detail["duration_s"] = round(time.time() - t0, 2)
    return detail


PROSE_HEAD = """# Alpha 门禁（5 条端到端工作流）

> 本文件由 `python tools/alpha_gate.py` **真机跑出来**（AutoCAD 2025 / R25.0 / `<<VANILLA>>`）。
> 不要手改：重跑命令即可刷新。最近一次运行：%(when)s。

## 什么是这道门禁

`tests/live_judges.py` 验的是**单条能力**（一条能力一个文档、建→读回→重开）。
但"每条能力都过"不等于"一条真实工作流能交付"——中间的状态污染、图层/布局残留、
出图设置串味，只有把多步串在**一个文档**里才暴露。

所以这里按 **5 条端到端工作流**验，每条的最后一步必须是**可交付产物**（PDF/DWG/DXF），
并且做重开一致性检查。**5 条全过才算 alpha**。

## 五条工作流

| # | 工作流 | 干什么 | 产出 |
|---|---|---|---|
""" + "".join(
    "| %s | %s | %s | %s |\n"
    % (wf["id"], wf["name"], wf["story"], " + ".join(wf["exports"]).upper())
    for wf in WORKFLOWS
) + """
## 判据（每条都查）

| 判据 | 含义 |
|---|---|
| `steps` | 所有步骤的能力 `build` 都无异常 |
| `model` | 模型空间实体数 ≥ 该工作流的要求（默认 1；纯纸空间工作流为 0） |
| `layouts` | 布局数 ≥ 要求（仅多布局工作流） |
| `artifact` | 导出文件存在且达标（PDF ≥ 5 KB，多页 PDF ≥ 2 KB，DWG/DXF ≥ 2 KB） |
| `reopen` | DWG/DXF 重开后实体数与存盘前一致（±1） |
| `pages` | PDF 页数符合预期（多布局工作流为 2） |

> 阈值不是拍脑袋：多页 PDF 的内容是两个圆，实测合并后 2.8 KB，所以下限取 2 KB；
> 单页零件图带图框/标注/文字，实测 5.6 KB，下限取 5 KB。改内容形态时要一起改 `MIN_BYTES`。

## 与 CADCraft 的 alpha gate 对照

CADCraft 的 5 条是**交互式制图软件**的准入（精确捕捉、标注、块、布局出图、无损存 DWG）；
我们的是**自动化交付链路**的准入（画→标→符号→图框→出图、表格、装配序号、多布局、电气）。
两者都要求"最后一步能交付"，但我们的链路短、判据硬（重开一致性必须有数）。
"""


def render_md(results: List[Dict[str, Any]], when: str, env_info: Dict[str, Any],
              total_s: float) -> str:
    passed = sum(1 for r in results if r["ok"])
    lines = [PROSE_HEAD % {"when": when}, ""]
    lines += ["## 本次结果：**%d/%d 通过**（总耗时 %.1fs）" % (passed, len(results), total_s), "",
              "| # | 工作流 | 结果 | 耗时 | 实体数 | 产物 | 失败项 |",
              "|---|---|---|---:|---:|---|---|"]
    for r in results:
        failed = [k for k, v in (r.get("checks") or {}).items() if not v]
        exports = r.get("export_list") or [r.get("export") or {}]
        art = "、".join("%s %.1fKB%s" % (
            e.get("kind"), (e.get("bytes") or 0) / 1024.0,
            (" %s页" % e["pages"]) if e.get("pages") else "")
            for e in exports if e.get("kind")) or "—"
        lines.append("| %s | %s | %s | %.1fs | %s | %s | %s |"
                     % (r["id"], r["name"], "**PASS**" if r["ok"] else "**FAIL**",
                        r.get("duration_s") or 0.0, r.get("model_count", "—"), art,
                        "、".join(failed) if failed else ("—" if not r.get("error") else "异常")))
    lines.append("")

    bad = [r for r in results if not r["ok"]]
    if bad:
        lines += ["### 失败详情", ""]
        for r in bad:
            lines.append("**%s %s**" % (r["id"], r["name"]))
            if r.get("error"):
                lines.append("")
                lines.append("```")
                lines.append(r["error"])
                if r.get("traceback"):
                    lines.append(r["traceback"].rstrip())
                lines.append("```")
            for k, v in (r.get("checks") or {}).items():
                if not v:
                    lines.append("- 判据 `%s` 未通过" % k)
            for note in r.get("notes") or []:
                lines.append("- note: %s" % note)
            lines.append("")
    else:
        lines += ["### 结论", "",
                  "**5 条工作流全部通过**，alpha 门禁达成：图示能力可以从零画到可交付文件，"
                  "且 DWG/DXF 重开后实体数一致。", ""]

    lines += ["## 环境", "",
              "| 项 | 值 |", "|---|---|",
              "| AutoCAD | %s |" % env_info.get("exe", "—"),
              "| profile | %s |" % (env_info.get("profile") or "—"),
              "| 启动方式 | %s |" % ("本次启动" if env_info.get("launched") else "附加到已运行实例"),
              "",
              "## 复跑", "",
              "```bash",
              "python tools/alpha_gate.py              # 全部 5 条",
              "python tools/alpha_gate.py --only W1,W4 # 只跑指定",
              "python tools/alpha_gate.py --keep       # 跑完不退出 AutoCAD",
              "```", "",
              "完整证据（每步 artifacts / 计时 / 导出路径）：`%(workdir)s/results.json`" % {
                  "workdir": env_info.get("workdir", "_scratch")},
              ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="alpha 门禁：5 条端到端工作流")
    ap.add_argument("--only", default=None, help="工作流 id，逗号分隔（W1,W4）")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--per-workflow-timeout", type=float, default=180.0)
    args = ap.parse_args(argv)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    workdir = args.workdir or os.path.join(ROOT, "_scratch", "alpha_%s" % stamp)
    os.makedirs(workdir, exist_ok=True)

    only = [k.strip() for k in args.only.split(",")] if args.only else None
    flows = [w for w in WORKFLOWS if not only or w["id"] in only]
    if not flows:
        print("没有匹配的工作流")
        return 2

    start_watchdog(args.per_workflow_timeout, workdir)
    sig_before = env_signature()
    info = launch.launch()
    app = info["app"]
    print("AutoCAD：%s（profile=%r）"
          % ("本次启动" if info["launched"] else "附加到已运行实例", info.get("profile")))

    results: List[Dict[str, Any]] = []
    t_all = time.time()
    runner = None
    rc = 0
    try:
        runner = CaseRunner(app, workdir, log=lambda m: print(m))
        runner.ensure_baseline_doc()
        app = com.refresh(app)
        profile = launch.read_profile(app)
        if profile is None or profile.strip() != env.REQUIRED_PROFILE:
            print("拒绝在非 %s 配置下跑（实际 %r）" % (env.REQUIRED_PROFILE, profile))
            return 4
        for wf in flows:
            print("\n>>> %s %s —— %s" % (wf["id"], wf["name"], wf["story"]))
            _WATCH.update(deadline=time.time() + args.per_workflow_timeout, what=wf["id"])
            res = run_workflow(runner, wf, workdir)
            _WATCH["deadline"] = 0.0
            results.append(res)
            print("    %s  %.1fs  实体 %s  失败项 %s"
                  % ("PASS" if res["ok"] else "FAIL", res["duration_s"],
                     res.get("model_count"),
                     [k for k, v in res["checks"].items() if not v] or "-"))
    except Exception as exc:                            # noqa: BLE001
        print("!! 跑工作流时异常：%s: %s" % (type(exc).__name__, exc))
        traceback.print_exc()
        rc = 1
    finally:
        try:
            if runner is not None and runner.baseline_doc is not None:
                from acadkit.judges.case import finish
                fin = finish(app, runner.baseline_doc,
                             quit_app=(info["launched"] and not args.keep))
                print("\n收尾：%s" % json.dumps(fin, ensure_ascii=False, default=str))
        except Exception as exc:                        # noqa: BLE001
            print("!! 收尾失败：%s: %s" % (type(exc).__name__, exc))

    total_s = time.time() - t_all
    payload = {
        "tool": "acadkit alpha gate",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "workdir": workdir,
        "autocad": {"launched": info.get("launched"), "exe": info.get("exe"),
                    "profile": info.get("profile")},
        "env_before": sig_before,
        "env_after": env_signature(),
        "total_s": round(total_s, 1),
        "results": [{k: v for k, v in r.items() if k != "traceback"} for r in results],
    }
    with open(os.path.join(workdir, "results.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)

    passed = sum(1 for r in results if r["ok"])
    print("\n合计 %d 条工作流：通过 %d / 失败 %d（%.1fs）"
          % (len(results), passed, len(results) - passed, total_s))

    if not args.no_write:
        md = render_md(results, time.strftime("%Y-%m-%d %H:%M"), info, total_s)
        with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(md)
        print("已写 %s" % os.path.relpath(OUT, ROOT))

    if results and not all(r["ok"] for r in results):
        rc = rc or 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
