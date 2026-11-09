"""`gxkit apply`：一条命令把一份 XML 变成"可交付的 .gx3 + 报告"。

用法：
    python -m gxkit apply --xml build.xml                  # 导入→编译→存盘→报告
    python -m gxkit apply --xml build.xml --out D:\\x.gx3
    python -m gxkit apply --xml build.xml --dry            # 只做离线预检，不开 GX Works3

报告同时打印到 stdout 并写到 `<workdir>/apply_report.json`。
退出码：0 = 全部检查通过；1 = 有失败项（XML 不合法 / 导入未生效 / 编译有错）。
"""

from __future__ import annotations

import json
import pathlib
import time

from . import inspect as I
from . import xmlgen


def check_xml(path: pathlib.Path) -> dict:
    """离线预检：XML 能不能解析、关键结构在不在（不开 GX Works3）。"""
    import xml.etree.ElementTree as ET

    problems: list[str] = []
    info: dict = {"path": str(path), "exists": path.exists(),
                  "bytes": path.stat().st_size if path.exists() else 0}
    if not path.exists():
        return {**info, "ok": False, "problems": ["文件不存在"]}

    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as exc:
        return {**info, "ok": False, "problems": ["XML 解析失败：%s" % exc]}

    ns = {"d": xmlgen.NS}
    types = root.find("d:Types", ns)
    instances = root.find("d:Instances", ns)
    if types is None:
        problems.append("缺 <Types>")
    if instances is None:
        problems.append("缺 <Instances>")

    programs = types.findall("d:GlobalNamespace/d:Program", ns) if types is not None else []
    gn = types.find("d:GlobalNamespace", ns) if types is not None else None
    order = [c.tag.split("}")[-1] for c in list(gn)] if gn is not None else []
    if "FunctionBlock" in order and "Program" in order and order.index("Program") > order.index("FunctionBlock"):
        problems.append("顺序错：<Program> 必须在 <FunctionBlock> 之前（否则整份导入被忽略）")

    cfg = instances.find("d:Configuration", ns) if instances is not None else None
    gv = cfg.find("d:GlobalVars", ns) if cfg is not None else None
    labels = gv.findall("d:Variable", ns) if gv is not None else []
    structs = gn.findall("d:DataTypeDecl", ns) if gn is not None else []
    blocks = gn.findall("d:FunctionBlock", ns) if gn is not None else []

    # 结构体成员里若有人「不是最后」的 AddData，会被静默丢弃
    for st in structs:
        spec = st.find("d:UserDefinedTypeSpec", ns)
        if spec is None:
            continue
        tags = [c.tag.split("}")[-1] for c in list(spec)]
        if "AddData" in tags and tags.index("AddData") != len(tags) - 1:
            problems.append("结构体 %s 的 <AddData> 不在最后（会被静默丢弃）" % st.get("name"))

    info.update({"programs": [p.get("name") for p in programs],
                 "function_blocks": [b.get("name") for b in blocks],
                 "structs": [s.get("name") for s in structs],
                 "global_labels": [v.get("name") for v in labels],
                 "gn_order": order})
    info["ok"] = not problems
    info["problems"] = problems
    return info


def apply(xml_path: pathlib.Path, out: pathlib.Path, workdir: pathlib.Path,
          keep: bool = False) -> int:
    """开 GX Works3：新建 → 另存 → 导入 → 全部转换 → 保存 → 读回，出报告。"""
    from .actions import _import_verified, _new_and_save
    from .session import Session
    from .win import kill_stray

    workdir.mkdir(parents=True, exist_ok=True)
    ctx = {"project": str(out), "workdir": str(workdir)}
    t0 = time.time()
    report: dict = {"xml": str(xml_path), "project": str(out),
                    "precheck": check_xml(xml_path)}
    if not report["precheck"]["ok"]:
        report["ok"] = False
        report["seconds"] = round(time.time() - t0, 1)
        _emit(report, workdir)
        return 1

    kill_stray()
    s, _ = _new_and_save(ctx)
    name = (report["precheck"]["programs"] or ["ProgApply"])[0]
    imp = _import_verified(s, ctx, xml_path, name)
    prog = I.read_progress(out)
    labels = I.read_labels(out)
    names = {r["value"] for r in labels if isinstance(r["value"], str)}
    sources = I.st_sources(out)
    stages = prog.get("stages") or []
    failed = [{"stage": x["stage"], "errors": x["errors"]} for x in stages if x["errors"]]

    report.update({
        "imported": bool(imp.get("opened") and imp.get("confirmed")),
        "attempts": imp.get("attempts"),
        "programs_in_project": I.program_names(out),
        "sources": len(sources),
        "steps": len(I.read_steps(out)),
        "labels": len(labels),
        "global_labels_landed": [n for n in report["precheck"]["global_labels"] if n in names],
        "errors": prog.get("errors"),
        "failed_stages": failed,
    })
    if not keep:
        s.close()
    ok = (report["imported"] and (report["errors"] == 0) and not failed
          and report["sources"] > 0)
    report["ok"] = bool(ok)
    report["seconds"] = round(time.time() - t0, 1)
    _emit(report, workdir)
    return 0 if ok else 1


def _emit(report: dict, workdir: pathlib.Path) -> None:
    (workdir / "apply_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    pre = report["precheck"]
    print("XML   : %s (%d bytes)" % (pre["path"], pre.get("bytes", 0)))
    print("  程序 %s | 功能块 %s | 结构体 %s | 全局标签 %s"
          % (pre.get("programs"), pre.get("function_blocks"),
             pre.get("structs"), pre.get("global_labels")))
    if pre.get("problems"):
        for p in pre["problems"]:
            print("  ! 预检：%s" % p)
    if "imported" in report:
        print("工程  : %s" % report["project"])
        print("  导入 %s（尝试 %s 次）| 程序 %s | 源码块 %d | 步 %d | 标签 %d"
              % (report["imported"], report.get("attempts"),
                 report.get("programs_in_project"), report["sources"],
                 report["steps"], report["labels"]))
        print("  编译错误 %s | 失败阶段 %s"
              % (report["errors"], [f["stage"] for f in report["failed_stages"]]))
        print("  全局标签落地：%s" % report["global_labels_landed"])
    print("结果  : %s（%.1f s）→ %s"
          % ("通过" if report["ok"] else "未通过", report["seconds"],
             workdir / "apply_report.json"))
