"""动作层：每条能力自己起一个干净的 GX Works3（避免跨能力的界面状态漂移）。

代价是每条 ~10 s 启动，换来的是"每次都是从零开始"的确定性。
"""

from __future__ import annotations

import pathlib
import time
import zipfile

from .session import Session, read_config, read_progress

ST_CODE = "B0 := NOT B0;\r\nW0 := W0 + 1;\r\n"

NEW = dict(series=3, model=0, lang=1)   # FX5CPU / FX5U / ST


def _boot(ctx: dict, project: str | None = None) -> Session:
    s = Session(project=project)
    info = s.start()
    ctx["session"] = s
    ctx["startup"] = info.get("startup_s")
    return s


def _new_and_save(ctx: dict) -> tuple[Session, dict]:
    """起会话 → 新建工程 → 另存为。新建失败就**重开会话**再来一次。

    踩过：刚杀完 GX Works3 立刻启动时，`Ctrl+N` 偶尔不弹对话框；
    重试 4 次仍不行，重开会话比继续等更可靠。
    """
    last: Exception | None = None
    for attempt in range(2):
        s = _boot(ctx)
        try:
            s.new_project(**NEW)
            saved = s.save_as(ctx["project"])
            return s, saved
        except RuntimeError as exc:
            last = exc
            try:
                s.close()
            except Exception:
                pass
            time.sleep(6 + attempt * 4)
    raise last or RuntimeError("新建工程失败")


def _new_project(ctx: dict) -> tuple[Session, dict]:
    """新建工程；对话框没弹出来就**重开会话**再试（冷启动时偶发）。"""
    last: Exception | None = None
    for attempt in range(2):
        s = _boot(ctx)
        try:
            return s, s.new_project(**NEW)
        except RuntimeError as exc:
            last = exc
            try:
                s.close()
            except Exception:
                pass
            time.sleep(8 + attempt * 4)
    raise last or RuntimeError("新建工程失败")


def project_new(ctx: dict) -> dict:
    s, proj = _new_project(ctx)
    title = proj.get("title") or ""
    return {"has_window": bool(title), "is_st": "ST" in title, "title": title,
            "startup_s": ctx.get("startup")}


def project_save(ctx: dict) -> dict:
    s, saved = _new_and_save(ctx)
    cfg = read_config(ctx["project"])
    return {"exists": saved["exists"], "bytes": saved["bytes"],
            "unit": cfg.get("Unit"),
            "readback_ok": str(saved["readback"]).lower().endswith(".gx3")}


def project_meta(ctx: dict) -> dict:
    s, _ = _new_and_save(ctx)
    cfg = read_config(ctx["project"])
    with zipfile.ZipFile(ctx["project"]) as z:
        names = z.namelist()
    return {"unit": cfg.get("Unit"), "zip_entries": len(names),
            "has_config": "!!Config.xml" in names}


def program_paste_st(ctx: dict) -> dict:
    s, _ = _new_and_save(ctx)
    _paste_until_steps(s, ctx.get("code") or ST_CODE)
    prog = read_progress(ctx["project"])
    return {"steps": s.steps(), "convert_errors": prog.get("errors"),
            "title": s.title()}


def build_convert_all(ctx: dict) -> dict:
    s, _ = _new_and_save(ctx)
    _paste_until_steps(s, ctx.get("code") or ST_CODE)
    s.save()
    prog = read_progress(ctx["project"])
    return {"errors": prog.get("errors"), "warnings": prog.get("warnings"),
            "stages": len(prog.get("stages") or []), "found": prog.get("found")}


def build_program_check(ctx: dict) -> dict:
    """已转换工程 → 工具·程序检查 → 执行 → 读判定文本。"""
    s, _ = _new_and_save(ctx)
    _paste_until_steps(s, ctx.get("code") or ST_CODE)
    s.save()
    res = s.program_check()
    prog = read_progress(ctx["project"])
    return {"opened": res.get("opened"), "clean": res.get("clean"),
            "check_errors": res.get("errors"), "verdict": res.get("verdict"),
            "convert_errors": prog.get("errors")}


BAD_ST_CODE = "B0 := ;\r\nW0 := W0 + ;\r\n"


def build_error_detail(ctx: dict) -> dict:
    """故意写错 → 转换 → 从 Progress.txt 读出"错在哪个阶段、错几个"。

    光有坏代码还不够：得先证明"粘贴这条通路是通的"（好代码能转出 N步），
    再贴坏代码。坏代码是否真的落地，用**读回的源码**确认（曾出现贴了没落地、
    转换仍然 0 错，于是误报"没有错误"）。
    """
    from . import inspect as I

    bad = ctx.get("code") or BAD_ST_CODE
    s, _ = _new_and_save(ctx)
    good_steps = _paste_until_steps(s, ST_CODE)

    prog: dict = {}
    for attempt in range(3):
        s.paste_st(bad)
        s.convert_all()
        s.save()
        prog = read_progress(ctx["project"])
        if I.source_matches(ctx["project"], bad) and prog.get("errors"):
            break
        if prog.get("errors") is None:
            s.convert_all()
            s.save()
            prog = read_progress(ctx["project"])
            if prog.get("errors"):
                break
        time.sleep(1.5)

    failed = prog.get("failed_stages") or []
    return {"errors": prog.get("errors"), "warnings": prog.get("warnings"),
            "failed_stage_count": len(failed),
            "failed_stage": failed[0] if failed else None,
            "stages": len(prog.get("stages") or []),
            "good_steps": good_steps,
            "bad_landed": I.source_matches(ctx["project"], bad),
            "progress_found": prog.get("found")}


def batch_projects(ctx: dict) -> dict:
    """同一会话里连做 N 个工程（粘贴不同参数 → 转换 → 菜单另存为）。"""
    count = int(ctx.get("batch_count") or 3)
    s, _ = _new_project(ctx)
    base = pathlib.Path(ctx["project"]).with_name("batch_base.gx3")
    s.save_as(base)

    def variant(i: int) -> str:
        # 变体长度随 i 增长，便于用"文件大小各不相同"反证内容真的换了
        lines = ["B0 := NOT B0;"] + ["W%d := W%d + %d;" % (i % 8, i % 8, k + 1)
                                     for k in range(i + 1)]
        return "\r\n".join(lines) + "\r\n"

    codes = [variant(i) for i in range(count)]
    items = []
    t0 = time.time()
    for i, code in enumerate(codes):
        path = pathlib.Path(ctx["project"]).with_name("batch_%d.gx3" % i)
        s.paste_st(code)
        s.convert_all()
        info = s.save_as(path, via_menu=True)
        prog = read_progress(path)
        items.append({"index": i, "exists": bool(info.get("exists")),
                      "bytes": info.get("bytes") or 0,
                      "errors": prog.get("errors"), "steps": s.steps()})
    # 反证"内容真的换了"：读回每份工程的 ST 源码，跟目标代码逐字比
    from . import inspect as I

    def norm(t: str) -> str:
        return t.replace("\r\n", "\n").strip()

    sources = []
    matched = 0
    for i, code in enumerate(codes):
        path = pathlib.Path(ctx["project"]).with_name("batch_%d.gx3" % i)
        got = I.st_source(path) if path.exists() else ""
        sources.append(norm(got))
        if got and norm(got) == norm(code):
            matched += 1
    clean = [x for x in items if x["exists"] and x["errors"] == 0]
    return {"items": len(items), "clean_items": len(clean),
            "seconds": round(time.time() - t0, 1),
            "distinct_sizes": len({x["bytes"] for x in items}),
            "distinct_sources": len(set(sources)),
            "content_match": matched}


def project_reopen(ctx: dict) -> dict:
    s, _ = _new_and_save(ctx)
    _paste_until_steps(s, ctx.get("code") or ST_CODE)
    s.save()
    before = s.steps()
    s.close()
    time.sleep(2)
    s2 = _boot(ctx, project=ctx["project"])
    title = s2.title() or ""
    return {"reopened": pathlib.Path(ctx["project"]).name in title,
            "steps_before": before, "steps": s2.steps(), "title": title}


def build_locate_error_line(ctx: dict) -> dict:
    """二分法定位"哪一行编译失败"。

    编译失败时 `T_Step` 是空的（没有步就没有源码坐标），编译器也不给行号，
    能拿到的事实只有"这段代码有 N 个错误"。于是用**前缀二分**去问编译器：

        前缀 lines[0:k] 通过、lines[0:k+1] 失败 → 第 k+1 行就是坏行

    前提是"错在前缀里就会一直错"，这对编译错误成立。
    """
    bad_line = int(ctx.get("bad_line") or 5)
    total = int(ctx.get("total_lines") or 8)
    pool = ["B0 := NOT B0;", "W0 := W0 + 1;", "W1 := W0 + 2;", "B1 := B0 AND X0;",
            "B2 := ;", "W2 := W1 * 2;", "B3 := NOT B1;", "W3 := W2 + 3;"]
    lines = list(pool[:total])
    if bad_line <= total:
        lines[bad_line - 1] = "B2 := ;"

    s, _ = _new_and_save(ctx)
    base = pathlib.Path(ctx["project"]).with_name("probe")
    calls: list[dict] = []

    def fails(k: int) -> bool:
        """前缀 k 行是否编译失败。拿不到编译结果就重试，绝不把"没读到"当成"通过"。"""
        errs = None
        prog: dict = {}
        actual = None
        for attempt in range(3):
            s.paste_st("\r\n".join(lines[:k]))
            s.convert_all(wait_s=8.0)
            # 每轮换文件名：GX Works3 还占着上一个；attempt 也进名字，避免 save_as 改名后撞车
            tmp = base.with_name("probe_%d_%d.gx3" % (k, attempt))
            info = s.save_as(tmp, via_menu=True)
            actual = pathlib.Path(info.get("path") or tmp)
            prog = read_progress(actual)
            if prog.get("found") and prog.get("errors") is not None:
                errs = prog["errors"]
                break
            time.sleep(1.5)
        if errs is None:
            raise RuntimeError("前缀 %d 行没拿到编译结果（文件=%s, silent=%s）"
                               % (k, getattr(actual, "name", None),
                                  None if actual is None else actual.exists()))
        calls.append({"k": k, "errors": errs, "file": actual.name})
        return bool(errs)

    lo, hi = 1, len(lines)
    found = None
    if fails(hi):
        while lo < hi:
            mid = (lo + hi) // 2
            if fails(mid):
                hi = mid
            else:
                lo = mid + 1
        found = lo
    return {"found_line": found, "expected_line": bad_line,
            "total_lines": len(lines), "iterations": len(calls),
            "history": calls,
            "line_text": lines[found - 1] if found else None}


# ACTIONS 表放在文件末尾（新动作函数定义在下面）



# ---------- 纯离线：只读 .gx3 ----------
def _paste_until_steps(s, code: str, attempts: int = 3) -> int | None:
    """粘贴并转换，直到标题出现 N步（粘贴偶尔没落焦点，必须重试）。"""
    steps = None
    for i in range(attempts):
        s.paste_st(code)
        s.convert_all()
        steps = s.steps()
        if steps:
            return steps
        s._focus()
        time.sleep(1.5)
    return steps


def _norm_src(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def _saved_program(ctx: dict) -> tuple[object, str]:
    """建工程 → 粘贴（带步数校验）→ 转换 → 保存并**读回确认**，返回 (session, 源码)。"""
    from . import inspect as I

    code = ctx.get("code") or ST_CODE
    s, _ = _new_and_save(ctx)
    for attempt in range(2):
        _paste_until_steps(s, code)
        s.save()
        if I.source_matches(ctx["project"], code):
            break
        s.convert_all()
        s.save()
    return s, code


def program_read_st(ctx: dict) -> dict:
    """把 ST 源码从保存后的 `.gx3` 里读回来，跟贴进去的逐字节比。"""
    from . import inspect as I

    s, code = _saved_program(ctx)
    sources = I.st_sources(ctx["project"])
    best = max(sources.values(), key=len) if sources else ""
    return {"readback_chars": len(best), "lines": len(best.splitlines()),
            "matches": I.source_matches(ctx["project"], code),
            "sources": len(sources),
            "steps": len(I.read_steps(ctx["project"])),
            "title_steps": s.steps()}


def inspect_source_map(ctx: dict) -> dict:
    """每个 MIL 步 → 源码坐标（Row/Col/StrLen）与片段。"""
    from . import inspect as I

    s, _ = _saved_program(ctx)
    steps = I.steps_with_source(ctx["project"])
    rows = [x.get("row") for x in steps if x.get("row")]
    with_snippet = [x for x in steps if x.get("snippet")]
    return {"steps": len(steps), "rows": len(set(rows)),
            "max_row": max(rows) if rows else 0,
            "snippets": len(with_snippet),
            "first_snippet": with_snippet[0]["snippet"] if with_snippet else None}


def inspect_devices(ctx: dict) -> dict:
    """FX5U 系统软元件模板（2935 行）+ 注释条数。"""
    from . import inspect as I

    s, _ = _new_and_save(ctx)
    dev = I.read_devices(ctx["project"])
    return {"device_rows": dev["rows"], "device_types": len(dev["types"]),
            "commented": dev["commented"], "unit": I.read_config(ctx["project"]).get("Unit")}


def inspect_mil(ctx: dict) -> dict:
    """编译后的 IL 文本：op 个数、指令条数随源码行数增长。"""
    from . import inspect as I

    s, _ = _saved_program(ctx)
    mil = I.read_mil(ctx["project"])
    text = mil[0]["data"] if mil else ""
    return {"mil_rows": len(mil), "mil_chars": len(text),
            "op_count": text.count("op="),
            "steps": len(I.read_steps(ctx["project"]))}


def label_import_xml(ctx: dict) -> dict:
    """导入"只有全局标签"的 XML，并从 LabelData 读回确认标签真的进了工程。"""
    from . import xmlgen
    from . import inspect as I

    s, _ = _new_and_save(ctx)
    before = len(I.read_labels(ctx["project"]))
    wanted = [item["name"] for item in xmlgen.DEFAULT_LABELS]
    imp = {}
    labels = []
    # 导入偶尔没落地（确认框没点到/被别的提示挡住）：用“读回来的标签数”当后置条件重试
    for attempt in range(2):
        xml = xmlgen.write(
            pathlib.Path(ctx["project"]).with_name("labels_%d.xml" % attempt))
        imp = s.import_xml(xml)
        s.convert_all()
        s.save()
        labels = I.read_labels(ctx["project"])
        names = {r["value"] for r in labels if isinstance(r["value"], str)}
        if sum(1 for n in wanted if n in names) >= len(wanted):
            break
    prog = read_progress(ctx["project"])
    names = {r["value"] for r in labels if isinstance(r["value"], str)}
    return {"imported": bool(imp.get("opened") and imp.get("confirmed")),
            "labels_before": before, "labels_after": len(labels),
            "labels_found": sum(1 for n in wanted if n in names),
            "errors": prog.get("errors"), "stages": len(prog.get("stages") or [])}


def _flat(text: str) -> str:
    """去掉全部空白，用来比较"代码是否真的进了工程"（导入会改写换行/空行）。"""
    return "".join(str(text).split())


def program_import_xml(ctx: dict) -> dict:
    """用 XML 建一个新程序（PrgGen），并读回确认：程序名进了列表、正文进了 STDB、0 错。

    注意只导入**一次**：导入会真的建程序，若判据误判而重试，会建出 PrgGen_2。
    """
    from . import xmlgen
    from . import inspect as I

    code = ctx.get("code") or "B0 := NOT B0;\r\nW0 := W0 + 1;"
    s, _ = _new_and_save(ctx)
    base_steps = len(I.read_steps(ctx["project"]))
    base_sources = len(I.st_sources(ctx["project"]))

    name = ctx.get("program_name") or "PrgGen"
    xml = xmlgen.write_program(
        pathlib.Path(ctx["project"]).with_name("prog.xml"), name, code)
    imp = s.import_xml(xml)

    # 导入后必须真的转换过，Progress.txt 才会出现程序清单；
    # 导入进度条刚消失就按 F4 有时会“转了个空”，所以按 Progress 是否存在重试
    for _ in range(3):
        s.convert_all(wait_s=12.0)
        s.save()
        if read_progress(ctx["project"]).get("found"):
            break

    names = I.program_names(ctx["project"])
    sources = I.st_sources(ctx["project"])
    flat = "".join(_flat(t) for t in sources.values())
    prog = read_progress(ctx["project"])
    return {"imported": bool(imp.get("opened") and imp.get("confirmed")),
            "program_created": name in names,
            "program_count": len(names),
            "names": names,
            "body_found": _flat(code) in flat,
            "st_sources": len(sources),
            "steps_added": len(I.read_steps(ctx["project"])) - base_steps,
            "new_sources": len(sources) - base_sources,
            "errors": prog.get("errors")}


ACTIONS = {
    "project_new": project_new,
    "project_save": project_save,
    "project_meta": project_meta,
    "program_paste_st": program_paste_st,
    "program_read_st": program_read_st,
    "program_import_xml": program_import_xml,
    "inspect_source_map": inspect_source_map,
    "inspect_devices": inspect_devices,
    "inspect_mil": inspect_mil,
    "build_convert_all": build_convert_all,
    "build_program_check": build_program_check,
    "build_error_detail": build_error_detail,
    "batch_projects": batch_projects,
    "label_import_xml": label_import_xml,
    "build_locate_error_line": build_locate_error_line,
    "project_reopen": project_reopen,
}
