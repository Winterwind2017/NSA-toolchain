"""动作层：每条能力自己起一个干净的 GX Works3（避免跨能力的界面状态漂移）。

代价是每条 ~10 s 启动，换来的是"每次都是从零开始"的确定性。
"""

from __future__ import annotations

import pathlib
import time
import zipfile

from .session import Session, read_config, read_progress

ST_CODE = "B0 := NOT B0;\r\nW0 := W0 + 1;\r\n"

NEW = dict(series=3, model=0, lang=1)   # FX5CPU(FX5U) / ST

# 系列索引（探针 95 实测，来自新建工程对话框的系列下拉框）
CPU_SERIES = {0: "MX控制器", 1: "RCPU", 2: "LHCPU", 3: "FX5CPU",
              4: "QCPU(Q模式)", 5: "LCPU", 6: "FXCPU", 7: "NCCPU"}


def _cpu(ctx: dict) -> dict:
    """从 ctx 取机型参数；没给就用 FX5U 默认。"""
    return {"series": int(ctx.get("series", NEW["series"])),
            "model": int(ctx.get("model", NEW["model"])),
            "lang": int(ctx.get("lang", NEW["lang"]))}


def _boot(ctx: dict, project: str | None = None) -> Session:
    """起会话；启动失败也要重试（残留实例会让第一次必然失败）。"""
    last: Exception | None = None
    for attempt in range(3):
        s = Session(project=project)
        try:
            info = s.start()
        except RuntimeError as exc:
            last = exc
            try:
                s.close()
            except Exception:
                pass
            time.sleep(4 + attempt * 4)
            continue
        ctx["session"] = s
        ctx["startup"] = info.get("startup_s")
        return s
    raise last or RuntimeError("GX Works3 启动失败")


def _new_and_save(ctx: dict) -> tuple[Session, dict]:
    """起会话 → 新建工程 → 另存为。新建失败就**重开会话**再来一次。

    踩过：刚杀完 GX Works3 立刻启动时，`Ctrl+N` 偶尔不弹对话框；
    重试 4 次仍不行，重开会话比继续等更可靠。
    """
    last: Exception | None = None
    for attempt in range(3):
        try:
            s = _boot(ctx)
            s.new_project(**_cpu(ctx))
            saved = s.save_as(ctx["project"])
            got = pathlib.Path(ctx["project"])
            if not got.exists() or got.stat().st_size < 100_000:
                raise RuntimeError("另存为没有产出文件：%s" % got)
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
    for attempt in range(3):
        try:
            s = _boot(ctx)
            return s, s.new_project(**_cpu(ctx))
        except RuntimeError as exc:
            last = exc
            try:
                s.close()
            except Exception:
                pass
            time.sleep(8 + attempt * 4)
    raise last or RuntimeError("新建工程失败")


def project_new_cpu(ctx: dict) -> dict:
    """按 ctx 里的 series/model 新建工程，并读回 `!!Config.xml` 证明机型真的换了。"""
    s, proj = _new_project(ctx)
    saved = s.save_as(ctx["project"])
    cfg = read_config(ctx["project"])
    title = proj.get("title") or ""
    return {"unit": cfg.get("Unit"), "unit_id": cfg.get("UnitId"),
            "series": _cpu(ctx)["series"], "model": _cpu(ctx)["model"],
            "series_name": CPU_SERIES.get(_cpu(ctx)["series"]),
            "is_st": "ST" in title, "exists": bool(saved.get("exists")),
            "bytes": saved.get("bytes") or 0}


def program_roundtrip_cpu(ctx: dict) -> dict:
    """在指定机型上跑一遍"粘贴 ST → 转换 → 存盘 → 读回源码"。"""
    from . import inspect as I

    s, _ = _new_and_save(ctx)
    code = ctx.get("code") or "B0 := NOT B0;\r\nW0 := W0 + 1;"
    s.paste_st(code)
    s.convert_all()
    s.save()
    prog = read_progress(ctx["project"])
    return {"unit": read_config(ctx["project"]).get("Unit"),
            "source_matches": I.source_matches(ctx["project"], code),
            "steps": len(I.read_steps(ctx["project"])),
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages")}


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


def _paste_verified(s, ctx: dict, code: str, attempts: int = 3) -> bool:
    """粘贴 ST 并读回校验；不匹配就覆盖重试（Ctrl+A 后粘贴是覆盖，不会追加）。"""
    from . import inspect as I

    for attempt in range(attempts):
        s.paste_st(code)
        s.convert_all()
        s.save()
        if I.source_matches(ctx["project"], code):
            return True
        time.sleep(1.5 + attempt)
    return False


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


UNDEF_CODE = "UndefLabel := 1;\r\nB0 := NOT B0;"


def build_error_messages(ctx: dict) -> dict:
    """读**编译器原话**（「输出」面板的表格）：结果/数据名/分类/内容/错误代码。"""
    from . import uia

    s, _ = _new_and_save(ctx)
    code = ctx.get("code") or UNDEF_CODE
    s.paste_st(code)
    s.convert_all()
    info = uia.output_rows(s.proc.pid)
    s.save()                     # Progress.txt 只在存盘时写入
    prog = read_progress(ctx["project"])
    rows = info["rows"]
    return {"pane_found": bool(info["pane"]),
            "header": info["header"],
            "rows": len(rows),
            "messages": [r.get("content") for r in rows],
            "categories": [r.get("category") for r in rows],
            "codes": [r.get("code") for r in rows],
            "data_names": [r.get("data") for r in rows],
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages")}


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
        _paste_until_steps(s, code)   # 带“标题出现 N步”的校验重试
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


def project_new_language(ctx: dict) -> dict:
    """按不同**程序语言**建工程（1=ST 2=SFC 3=FBD），逐个存盘并核对标题/机型。"""
    langs = ctx.get("langs") or [1, 2, 3]
    marks = {1: "[ST]", 2: "[SFC]", 3: "[FBD"}
    s, _ = _new_and_save(ctx)
    made = []
    for idx, lang in enumerate(langs):
        if idx:
            s.close_project()
            time.sleep(1.5)
            title = s.new_project(series=int(ctx.get("series", 3)),
                                  model=int(ctx.get("model", 0)),
                                  lang=int(lang)).get("title") or ""
        else:
            title = s.title()
        path = pathlib.Path(ctx["project"]).with_name("lang_%d.gx3" % int(lang))
        s.save_as(path)
        cfg = read_config(path)
        made.append({"lang": int(lang), "title": title,
                     "mark": marks[int(lang)] in title,
                     "exists": path.exists(), "unit": cfg.get("Unit")})
    return {"made": len(made),
            "all_marks": all(m["mark"] for m in made),
            "all_exist": all(m["exists"] for m in made),
            "all_fx5u": all(m["unit"] == "FX5U" for m in made),
            "detail": made}


def project_check(ctx: dict) -> dict:
    """**工程校验**：把当前工程与另一个 .gx3 比对，读「校验结果」页的表格。"""
    import ctypes

    from . import inspect as I
    from . import uia
    from . import win as W

    u32 = ctypes.windll.user32
    s, _ = _new_and_save(ctx)
    base = pathlib.Path(ctx["project"]).with_name("check_base.gx3")
    s.save_as(base)
    s.paste_st(ctx.get("code_src") or "B0 := NOT B0;\r\nW0 := W0 + 1;")
    s.convert_all()
    s.save()
    other = pathlib.Path(ctx["project"]).with_name("check_other.gx3")
    s.save_as(other)
    s.paste_st(ctx.get("code_dst") or "B0 := NOT B0;")
    s.convert_all()
    s.save()

    # 工程 → 工程校验
    W.post_alt_letter(s.main["hwnd"], "P")
    time.sleep(0.7)
    opened = uia.invoke_menu_item("工程校验")
    time.sleep(2.0)
    dialogs = [w["hwnd"] for w in W.windows(s.proc.pid) if w["class"] == "#32770"]
    dlg = next((h for h in dialogs
                if "工程校验" in next((w["title"] for w in W.windows(s.proc.pid)
                                       if w["hwnd"] == h), "")), 0)
    if not dlg:
        return {"opened": opened, "result_doc": False, "rows": 0,
                "diff_count": None, "dialogs": len(dialogs)}
    # 点「...」→ 文件对话框 → 文件名框粘贴路径 → 回车
    btn = next((w["hwnd"] for w in W.windows(s.proc.pid)
                if w["class"] == "Button" and (w["title"] or "").strip() == "..."), 0)
    if not btn:
        btn = _find_button(dlg, "...")
    if btn:
        r = _rect(btn)
        W.click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, settle=0.6)
        time.sleep(2.0)
        fdlg = next((w["hwnd"] for w in W.windows(s.proc.pid)
                     if w["class"] == "#32770" and w["hwnd"] != dlg), 0)
        if fdlg:
            combo = _widest_lower_combo(fdlg)
            if combo:
                r = _rect(combo)
                W.click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, settle=0.5)
                W.set_clipboard(str(base))
                time.sleep(0.3)
                W.chord("ctrl", "v")
                time.sleep(0.6)
                W.tap("enter", 2.5)
    # 点「校验」
    chk = _find_button(dlg, "校验")
    if chk:
        r = _rect(chk)
        W.click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, settle=0.6)
        time.sleep(10.0)

    doc = uia.mdi_child(s.proc.pid, "校验结果")
    rows = uia.grid_rows(doc)["rows"] if doc else []
    diff = sum(1 for row in rows if row and "不一致" in "".join(row))
    status = _child_texts(doc) if doc else []
    note = next((x for x in status if "不同内容" in x), "")
    count = None
    if "存在" in note:
        digits = "".join(ch for ch in note.split("不同内容")[0] if ch.isdigit())
        count = int(digits) if digits else None
    return {"opened": opened, "result_doc": bool(doc), "rows": len(rows),
            "diff_count": diff if diff else count,
            "grid_diff": diff, "status_note": note, "status_count": count,
            "diffs": [r[:5] for r in rows if "不一致" in "".join(r)][:5],
            "errors": read_progress(base).get("errors")}


def _child_texts(hwnd: int) -> list[str]:
    """枚举子控件文本（结果页底部的状态行常是普通 Static/Edit）。"""
    import win32gui

    out = []

    def cb(h, _):
        txt = win32gui.GetWindowText(h)
        if txt:
            out.append(txt.strip())
        return True

    try:
        win32gui.EnumChildWindows(hwnd, cb, None)
    except Exception:
        pass
    return out


def _rect(hwnd: int):
    import win32gui
    return win32gui.GetWindowRect(hwnd)


def _find_button(parent: int, label: str) -> int:
    import win32gui
    hits = []

    def cb(h, _):
        if win32gui.GetClassName(h) == "Button" and win32gui.GetWindowText(h).strip() == label:
            hits.append(h)
        return True

    win32gui.EnumChildWindows(parent, cb, None)
    return hits[0] if hits else 0


def _widest_lower_combo(parent: int) -> int:
    import win32gui
    p = _rect(parent)
    best, bestw = 0, 0
    hits = []

    def cb(h, _):
        if win32gui.GetClassName(h) == "ComboBox":
            hits.append(h)
        return True

    win32gui.EnumChildWindows(parent, cb, None)
    for h in hits:
        r = _rect(h)
        w = r[2] - r[0]
        if w > 150 and r[1] > p[1] + (p[3] - p[1]) * 0.45 and w > bestw:
            best, bestw = h, w
    return best


def batch_new_projects(ctx: dict) -> dict:
    """同一会话连做 N 个新建工程：保存 → 关闭工程 → Ctrl+N → 另存为 → 写入 → 转换 → 校验。"""
    from . import inspect as I
    from . import xmlgen

    count = int(ctx.get("count") or 3)
    s, _ = _new_and_save(ctx)
    made = []
    for i in range(count):
        if i:
            s.close_project()
            time.sleep(1.5)
            s.new_project(**_cpu(ctx))
        path = pathlib.Path(ctx["project"]).with_name("batch_new_%d.gx3" % i)
        s.save_as(path)
        code = "W%d := W%d + %d;\r\n" % (i, i, i + 1)
        s.paste_st(code)
        s.convert_all()
        s.save()
        prog = read_progress(path)
        made.append({"i": i, "exists": path.exists(),
                     "src_match": I.source_matches(path, code),
                     "errors": prog.get("errors")})
    return {"made": len(made),
            "all_exist": all(m["exists"] for m in made),
            "all_src": all(m["src_match"] for m in made),
            "all_clean": all(m["errors"] == 0 for m in made),
            "detail": made}


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


def _import_labels_verified(s, ctx: dict, xml_path, want: list[str],
                            attempts: int = 2) -> int:
    """导入全局标签，若一个都没落地就重试（安全：上一次确实没写进去）。"""
    from . import inspect as I

    for attempt in range(attempts):
        s.import_xml(xml_path)
        s.convert_all(wait_s=12.0)
        s.save()
        names = {r["value"] for r in I.read_labels(ctx["project"])
                 if isinstance(r["value"], str)}
        landed = sum(1 for n in want if n in names)
        if landed == len(want):
            return landed
    return landed


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


def program_import_fb(ctx: dict) -> dict:
    """用 XML 一次建出"带局部标签的程序 + 一个功能块"，并读回确认三样东西都落地。"""
    from . import xmlgen
    from . import inspect as I

    code = ctx.get("code") or "LocBool := NOT LocBool;\r\nLocWord := LocWord + 1;"
    fb_code = ctx.get("fb_code") or "FB_Bool := NOT FB_Bool;\r\nFB_Word := FB_Word + 1;"
    s, _ = _new_and_save(ctx)
    base_labels = len(I.read_labels(ctx["project"]))
    base_sources = len(I.st_sources(ctx["project"]))

    xml = xmlgen.write_fb_program(
        pathlib.Path(ctx["project"]).with_name("fb.xml"),
        ctx.get("program_name") or "PrgFB", code,
        ctx.get("fb_name") or "FBGen", fb_code)
    imp = s.import_xml(xml)
    for _ in range(3):
        s.convert_all(wait_s=12.0)
        s.save()
        if read_progress(ctx["project"]).get("found"):
            break

    names = I.program_names(ctx["project"])
    sources = I.st_sources(ctx["project"])
    flat = "".join(I.flat(v) for v in sources.values())
    labels = set(I.label_names(ctx["project"]))
    prog = read_progress(ctx["project"])
    want_locals = [x["name"] for x in xmlgen.DEFAULT_LOCALS]
    want_fb = [x["name"] for x in xmlgen.DEFAULT_FB_LOCALS]
    return {"imported": bool(imp.get("opened") and imp.get("confirmed")),
            "program_created": "PrgFB" in names,
            "program_count": len(names),
            "names": names,
            "body_found": I.flat(code) in flat,
            "fb_body_found": I.flat(fb_code) in flat,
            "locals_found": sum(1 for n in want_locals if n in labels),
            "fb_vars_found": sum(1 for n in want_fb if n in labels),
            "labels_before": base_labels,
            "labels_after": len(I.read_labels(ctx["project"])),
            "new_sources": len(sources) - base_sources,
            "errors": prog.get("errors")}


def _import_verified(s, ctx: dict, xml_path, name: str, attempts: int = 2) -> dict:
    """导入 XML，并在"什么都没进"时重试。

    导入有静默失败（对话框确认没落到、整份被忽略）：工程里**一点变化都没有**。
    这种情况重试是安全的——因为上一次确实什么都没写进去。
    只要检测到目标程序出现，就绝不重试（导入非幂等，重试会得到 xxx_2）。
    """
    from . import inspect as I

    base_names = I.program_names(ctx["project"])
    base_sources = len(I.st_sources(ctx["project"]))
    info: dict = {}
    for attempt in range(attempts):
        info = s.import_xml(xml_path)
        for _ in range(3):
            s.convert_all(wait_s=12.0)
            s.save()
            if read_progress(ctx["project"]).get("found"):
                break
        names = I.program_names(ctx["project"])
        sources = len(I.st_sources(ctx["project"]))
        if name in names or sources > base_sources:
            info["attempts"] = attempt + 1
            return info
        time.sleep(1.5)
    info["attempts"] = attempts
    return info


def inspect_devices_cpu(ctx: dict) -> dict:
    """指定机型工程的软元件模板（`*_DC.db` 的 DEVICE_DATA），并和 FX5U 对比。"""
    from . import inspect as I

    s, _ = _new_and_save(ctx)
    info = I.read_devices(ctx["project"], limit=5)
    types = info.get("types") or []
    codes = sorted({t if isinstance(t, int) else t.get("code") for t in types}) \
        if isinstance(types, list) else sorted(types)
    return {"unit": read_config(ctx["project"]).get("Unit"),
            "rows": info.get("rows"),
            "device_type_codes": len(codes),
            "has_type_35": 35 in codes,
            "commented": info.get("commented")}


def xmlgen_manual_template(ctx: dict) -> dict:
    """用**手写骨架**（templates/base.xml，不读 MELSOFT 样例）建程序+FB，验证局部标签落地。"""
    from . import inspect as I
    from . import xmlgen

    s, _ = _new_and_save(ctx)
    try:
        xmlgen.use_manual_template()
        xml = xmlgen.write_fb_instance(
            pathlib.Path(ctx["project"]).with_name("manual_tpl.xml"),
            "PrgMT", "LocBool := NOT LocBool;", fb_name="FBInst", inst_name="InstFB")
        template_used = str(xmlgen.template_path())
    finally:
        xmlgen._SKELETON_CACHE = None          # 复位到默认骨架
    info = _import_verified(s, ctx, xml, "PrgMT")
    names = {r["value"] for r in I.read_labels(ctx["project"])
             if isinstance(r["value"], str)}
    prog = read_progress(ctx["project"])
    return {"template": pathlib.Path(template_used).name,
            "uses_manual": "base.xml" in template_used,
            "program_created": "PrgMT" in I.program_names(ctx["project"]),
            "locals_found": sum(1 for n in ("LocBool", "LocWord") if n in names),
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages"),
            "attempts": info.get("attempts")}


def datatype_struct_array(ctx: dict) -> dict:
    """结构体带**数组成员**（ARRAY[0..3] OF BOOL），并通过全局标签访问元素。"""
    from . import inspect as I
    from . import xmlgen

    s, _ = _new_and_save(ctx)
    members = ctx.get("members") or [
        {"name": "MyBool", "type": "BOOL"},
        {"name": "Arr", "type": "BOOL", "array": [0, 3]}]
    assign = ctx.get("assign") or [{"name": "MyBool", "address": "B0"},
                                   {"name": "Arr", "address": "B10"}]
    code = ctx.get("code") or "GS1.Arr[0] := TRUE;\r\nGS1.MyBool := NOT GS1.MyBool;"
    xml = xmlgen.write_struct_global_program(
        pathlib.Path(ctx["project"]).with_name("struct_array.xml"),
        "PrgArr", code, "StructArr", "GS1", members=members, assign=assign)
    info = _import_verified(s, ctx, xml, "PrgArr")
    prog = read_progress(ctx["project"])
    stages = prog.get("stages") or []
    struct_stage = next((x for x in stages if "结构体" in x["stage"]), None)
    src = I.st_source(ctx["project"])
    return {"program_created": "PrgArr" in I.program_names(ctx["project"]),
            "struct_stage_seen": struct_stage is not None,
            "struct_stage_errors": (struct_stage or {}).get("errors"),
            "array_access_in_source": "Arr[" in src,
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages"),
            "attempts": info.get("attempts")}


def program_edit_existing(ctx: dict) -> dict:
    """**改写已有程序**：XML 建 PrgOne(正文A) → 双击打开它 → 粘正文B → 转换 → 读回。"""
    from . import inspect as I
    from . import uia
    from . import xmlgen

    s, _ = _new_and_save(ctx)
    code_a = ctx.get("code_a") or "B0 := NOT B0;"
    code_b = ctx.get("code_b") or "W0 := W0 + 7;\r\nW1 := W0;"
    xml = xmlgen.write_program(pathlib.Path(ctx["project"]).with_name("edit1.xml"),
                               "PrgOne", code_a)
    _import_verified(s, ctx, xml, "PrgOne")
    counts_before = len(I.program_names(ctx["project"]))
    a_before = I.source_matches(ctx["project"], code_a)

    opened = uia.open_program(s.proc.pid, "PrgOne")
    if not opened["opened"]:
        return {"opened": False, "title": opened["title"],
                "programs_before": counts_before, "a_before": a_before,
                "b_after": False, "a_gone": False, "programs_after": counts_before,
                "errors": None}

    _paste_verified(s, ctx, code_b)
    s.save()
    prog = read_progress(ctx["project"])
    return {"opened": True, "title": opened["title"], "offset": opened["offset"],
            "programs_before": counts_before,
            "a_before": a_before,
            "programs_after": len(I.program_names(ctx["project"])),
            "b_after": I.source_matches(ctx["project"], code_b),
            "a_gone": not I.source_matches(ctx["project"], code_a),
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages")}


def program_multi_programs(ctx: dict) -> dict:
    """一个工程里放**两个程序**（各导入一次 XML），验证互不干扰。"""
    from . import inspect as I
    from . import xmlgen

    s, _ = _new_and_save(ctx)
    code1 = ctx.get("code") or "B0 := NOT B0;"
    code2 = ctx.get("code2") or "W0 := W0 + 1;\r\nW1 := W0;"
    p1 = xmlgen.write_program(pathlib.Path(ctx["project"]).with_name("prog1.xml"),
                              "PrgOne", code1)
    _import_verified(s, ctx, p1, "PrgOne")
    p2 = xmlgen.write_program(pathlib.Path(ctx["project"]).with_name("prog2.xml"),
                              "PrgTwo", code2)
    _import_verified(s, ctx, p2, "PrgTwo")
    prog = read_progress(ctx["project"])
    names = I.program_names(ctx["project"])
    sources = [I.flat(v) for v in I.st_sources(ctx["project"]).values()]
    return {"both_created": ("PrgOne" in names) and ("PrgTwo" in names),
            "one_in_source": I.flat(code1) in sources,
            "two_in_source": I.flat(code2) in sources,
            "program_count": len(names),
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages")}


def program_import_fb_params(ctx: dict) -> dict:
    """导入"带参数的功能块 + 程序里实例化并传参"，并读回验证。"""
    from . import inspect as I
    from . import xmlgen

    s, _ = _new_and_save(ctx)
    call = ctx.get("code") or (
        "InstFB(fbIn := B0, fbOut => B1, fbOutR => B2);")
    xml = xmlgen.write_fb_params_program(
        pathlib.Path(ctx["project"]).with_name("fb_params.xml"),
        "PrgFP", call, fb_name="FBParam", inst_name="InstFB",
        fb_body=ctx.get("fb_body") or "fbOut := fbIn;\r\nfbOutR := fbOut;")
    info = _import_verified(s, ctx, xml, "PrgFP")
    prog = read_progress(ctx["project"])
    names = I.program_names(ctx["project"])
    flat = I.flat(I.st_source(ctx["project"]))
    return {"program_created": "PrgFP" in names,
            "fb_created": "FBParam" in names,
            "call_in_source": I.flat(call) in flat,
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages"),
            "attempts": info.get("attempts")}


def datatype_import(ctx: dict) -> dict:
    """用 XML 建结构体（StructGen），并用**导航树**把它读回来确认。

    为什么不用"结构体类型的变量"当判据：实测 S1 : StructGen 会让
    局部标签(PrgS4)定义检查中 报 1 个错（结构体标签需要成员级软元件分配），
    而结构体本身是进得去的。所以判据改成 UIA 导航树里出现 StructGen。
    """
    from . import xmlgen
    from . import inspect as I
    from . import uia

    s, _ = _new_and_save(ctx)
    base_labels = len(I.read_labels(ctx["project"]))
    xml = xmlgen.write_struct_program(
        pathlib.Path(ctx["project"]).with_name("struct.xml"),
        ctx.get("program_name") or "PrgStruct", ctx.get("code") or "LocBool := NOT LocBool;",
        ctx.get("struct_name") or "StructGen",
        members=None,          # None = 保留样例成员原样（改成员会让整份导入被丢弃）
        locals_=[{"name": "LocBool", "type": "BOOL"}])
    imp = _import_verified(s, ctx, xml, ctx.get("program_name") or "PrgStruct")
    names = I.program_names(ctx["project"])
    nodes = []
    try:
        nodes = uia.find_names(s.main["hwnd"], ctx.get("struct_name") or "StructGen")
    except Exception:
        nodes = []
    prog = read_progress(ctx["project"])
    return {"imported": bool(imp.get("opened") and imp.get("confirmed")),
            "attempts": imp.get("attempts"),
            "program_created": "PrgStruct" in names,
            "programs": names,
            "struct_node_seen": bool(nodes),
            "struct_nodes": nodes[:3],
            "labels_before": base_labels,
            "labels_after": len(I.read_labels(ctx["project"])),
            "errors": prog.get("errors")}


def program_import_fb_instance(ctx: dict) -> dict:
    """建功能块 + 程序里声明其实例并调用（InstFB();）。"""
    from . import xmlgen
    from . import inspect as I

    code = ctx.get("code") or "InstFB();"
    fb_code = ctx.get("fb_code") or "FB_Bool := NOT FB_Bool;"
    s, _ = _new_and_save(ctx)
    base_sources = len(I.st_sources(ctx["project"]))
    xml = xmlgen.write_fb_instance(
        pathlib.Path(ctx["project"]).with_name("fbinst.xml"),
        ctx.get("program_name") or "PrgFB", code,
        ctx.get("fb_name") or "FBInst", ctx.get("inst_name") or "InstFB",
        fb_body=fb_code,
        locals_=[{"name": "LocBool", "type": "BOOL"}])
    imp = _import_verified(s, ctx, xml, ctx.get("program_name") or "PrgFB")
    names = I.program_names(ctx["project"])
    labels = I.read_labels(ctx["project"])
    types = [r["value"] for r in labels
             if r.get("column_id") == 3 and isinstance(r.get("value"), str)]
    flat = "".join(I.flat(v) for v in I.st_sources(ctx["project"]).values())
    prog = read_progress(ctx["project"])
    return {"imported": bool(imp.get("opened") and imp.get("confirmed")),
            "attempts": imp.get("attempts"),
            "program_created": "PrgFB" in names,
            "programs": names,
            "body_found": I.flat(code) in flat,
            "fb_body_found": I.flat(fb_code) in flat,
            "instance_type_seen": (ctx.get("fb_name") or "FBInst") in types,
            "new_sources": len(I.st_sources(ctx["project"])) - base_sources,
            "errors": prog.get("errors")}


def datatype_member_var(ctx: dict) -> dict:
    """结构体 + 结构体类型的变量（带成员级软元件分配），一份文档导入并读回。"""
    from . import xmlgen
    from . import inspect as I
    from . import uia

    name = ctx.get("program_name") or "PrgSV"
    s, _ = _new_and_save(ctx)
    base_labels = len(I.read_labels(ctx["project"]))
    xml = xmlgen.write_struct_var_program(
        pathlib.Path(ctx["project"]).with_name("struct_var.xml"),
        name, ctx.get("struct_name") or "StructGen",
        ctx.get("var_name") or "S1",
        ctx.get("code") or "LocBool := NOT LocBool;")
    imp = _import_verified(s, ctx, xml, name)

    names = I.program_names(ctx["project"])
    prog = read_progress(ctx["project"])
    labels = I.read_labels(ctx["project"])
    label_names = {r["value"] for r in labels if isinstance(r["value"], str)}
    members = ["member1_1", "member1_2", "member1_3", "member1_4",
               "member2_1", "member2_2", "member2_3"]
    nodes = []
    try:
        nodes = uia.find_names(s.main["hwnd"], ctx.get("struct_name") or "StructGen")
    except Exception:
        nodes = []
    stages = prog.get("stages") or []
    define_stage = next((x for x in stages
                         if x["stage"] == "局部标签(%s)定义检查中" % name), None)
    return {"imported": bool(imp.get("opened") and imp.get("confirmed")),
            "attempts": imp.get("attempts"),
            "program_created": name in names,
            "programs": names,
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages"),
            "define_stage_seen": define_stage is not None,
            "define_stage_errors": (define_stage or {}).get("errors"),
            "struct_node_seen": bool(nodes),
            "member_rows_seen": sum(1 for m in members if m in label_names),
            "labels_before": base_labels,
            "labels_after": len(labels)}


CUSTOM_MEMBERS = [
    {"name": "MyBool", "type": "BOOL", "init": "FALSE"},
    {"name": "MyWord", "type": "WORD", "init": "0"},
]


def datatype_custom_members(ctx: dict) -> dict:
    """自定义结构体成员（MyBool / MyWord）+ 结构体变量，一份文档导入并读回。"""
    from . import xmlgen
    from . import inspect as I
    from . import uia

    name = ctx.get("program_name") or "PrgCust"
    struct_name = ctx.get("struct_name") or "StructCust"
    members = ctx.get("members") or CUSTOM_MEMBERS
    s, _ = _new_and_save(ctx)
    base_labels = len(I.read_labels(ctx["project"]))
    xml = xmlgen.write_struct_var_program(
        pathlib.Path(ctx["project"]).with_name("custom_members.xml"),
        name, struct_name, ctx.get("var_name") or "S1",
        ctx.get("code") or "LocBool := NOT LocBool;",
        members=members)
    imp = _import_verified(s, ctx, xml, name)

    prog = read_progress(ctx["project"])
    labels = I.read_labels(ctx["project"])
    label_names = {r["value"] for r in labels if isinstance(r["value"], str)}
    nodes = []
    try:
        nodes = uia.find_names(s.main["hwnd"], struct_name)
    except Exception:
        nodes = []
    return {"imported": bool(imp.get("opened") and imp.get("confirmed")),
            "attempts": imp.get("attempts"),
            "program_created": name in I.program_names(ctx["project"]),
            "programs": I.program_names(ctx["project"]),
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages"),
            "member_rows_seen": sum(1 for m in members if m["name"] in label_names),
            "member_names": [m["name"] for m in members],
            "struct_node_seen": bool(nodes),
            "labels_before": base_labels,
            "labels_after": len(labels)}


def datatype_member_access(ctx: dict) -> dict:
    """结构体成员按名字访问（GS1.MyBool := ...）——必须走**全局**结构体标签。"""
    from . import xmlgen
    from . import inspect as I

    name = ctx.get("program_name") or "PrgGA"
    struct_name = ctx.get("struct_name") or "StructCust"
    label = ctx.get("label_name") or "GS1"
    members = ctx.get("members") or CUSTOM_MEMBERS
    code = ctx.get("code") or (label + ".MyBool := NOT " + label + ".MyBool;")
    s, _ = _new_and_save(ctx)
    base_labels = len(I.read_labels(ctx["project"]))
    xml = xmlgen.write_struct_global_program(
        pathlib.Path(ctx["project"]).with_name("global_struct.xml"),
        name, code, struct_name, label, members=members)
    imp = _import_verified(s, ctx, xml, name)

    prog = read_progress(ctx["project"])
    stages = prog.get("stages") or []
    define = next((x for x in stages
                   if x["stage"] == "结构体(%s)的定义检查中" % struct_name), None)
    labels = I.read_labels(ctx["project"])
    label_names = {r["value"] for r in labels if isinstance(r["value"], str)}
    flat = "".join(I.flat(v) for v in I.st_sources(ctx["project"]).values())
    types = [r["value"] for r in labels
             if r.get("column_id") == 3 and isinstance(r.get("value"), str)]
    return {"imported": bool(imp.get("opened") and imp.get("confirmed")),
            "attempts": imp.get("attempts"),
            "program_created": name in I.program_names(ctx["project"]),
            "programs": I.program_names(ctx["project"]),
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages"),
            "struct_define_stage_seen": define is not None,
            "struct_define_stage_errors": (define or {}).get("errors"),
            "member_access_in_source": I.flat(code) in flat,
            "global_label_seen": label in label_names,
            "struct_type_in_labels": struct_name in types,
            "labels_before": base_labels,
            "labels_after": len(labels)}


MULTI_TYPE_LABELS = [
    {"name": "LBL_BOOL", "type": "BOOL", "address": "M50", "init": "FALSE"},
    {"name": "LBL_WORD", "type": "WORD", "address": "W0", "init": "0"},
    {"name": "LBL_DWORD", "type": "DWORD", "address": "D0", "init": "0"},
]


def label_multi_type(ctx: dict) -> dict:
    """导入 BOOL / WORD / DWORD 三种全局标签，再导入一个用 WORD 标签的程序。"""
    from . import xmlgen
    from . import inspect as I

    s, _ = _new_and_save(ctx)
    base_labels = len(I.read_labels(ctx["project"]))

    want = [x["name"] for x in (ctx.get("labels") or MULTI_TYPE_LABELS)]
    labels_path = xmlgen.write(
        pathlib.Path(ctx["project"]).with_name("multi_labels.xml"),
        ctx.get("labels") or MULTI_TYPE_LABELS)
    _import_labels_verified(s, ctx, labels_path, want)

    names = {r["value"] for r in I.read_labels(ctx["project"])
             if isinstance(r["value"], str)}
    landed = sum(1 for n in want if n in names)
    labels_after = len(I.read_labels(ctx["project"]))

    # 再用 WORD 标签写一段程序，证明它真的能用
    prog_name = "PrgType"
    prog_xml = xmlgen.write_program(
        pathlib.Path(ctx["project"]).with_name("type_prog.xml"),
        prog_name, ctx.get("code") or "LBL_WORD := LBL_WORD + 1;")
    s.import_xml(prog_xml)
    for _ in range(3):
        s.convert_all(wait_s=12.0)
        s.save()
        if read_progress(ctx["project"]).get("found"):
            break

    prog = read_progress(ctx["project"])
    flat = "".join(I.flat(v) for v in I.st_sources(ctx["project"]).values())
    return {"labels_landed": landed,
            "labels_wanted": len(want),
            "labels_before": base_labels,
            "labels_after": labels_after,
            "program_created": prog_name in I.program_names(ctx["project"]),
            "word_used_in_source": I.flat("LBL_WORD := LBL_WORD + 1;") in flat,
            "errors": prog.get("errors"),
            "failed_stages": prog.get("failed_stages")}


def inspect_programs(ctx: dict) -> dict:
    """列程序清单（步数 / 源码行数 / 正文），数据全来自 .gx3 里的 SQLite。"""
    from . import inspect as I

    s, _ = _new_and_save(ctx)
    code = ctx.get("code") or "B0 := NOT B0;\r\nW0 := W0 + 1;"
    _paste_until_steps(s, code)   # 带“标题出现 N步”的校验重试
    s.save()

    info = I.program_list(ctx["project"])
    return {"program_count": info["program_count"],
            "programs": info["programs"],
            "source_count": info["source_count"],
            "matched_blocks": info["matched_blocks"],
            "total_steps": info["total_steps"],
            "body_found": I.source_matches(ctx["project"], code),
            "max_lines": max([x["lines"] for x in info["sources"]] or [0])}


def project_diff_action(ctx: dict) -> dict:
    """两个工程做源码级差异：先存 A，改代码另存 B，再 diff A/A（应为一致）与 A/B。"""
    from . import inspect as I

    s, _ = _new_project(ctx)
    code_a = ctx.get("code_a") or "B0 := NOT B0;"
    code_b = ctx.get("code_b") or "B0 := NOT B0;\r\nW0 := W0 + 1;"
    pa = pathlib.Path(ctx["project"]).with_name("diff_a.gx3")
    pb = pathlib.Path(ctx["project"]).with_name("diff_b.gx3")
    s.paste_st(code_a)
    s.convert_all()
    s.save_as(pa, via_menu=True)
    s.paste_st(code_b)
    s.convert_all()
    s.save_as(pb, via_menu=True)

    same = I.project_diff(pa, pa)
    diff = I.project_diff(pa, pb)
    return {"identical_self": same["identical"],
            "blocks_changed": diff["blocks_changed"],
            "changed_added": sum(c["added"] for c in diff["changed"]),
            "changed_removed": sum(c["removed"] for c in diff["changed"]),
            "programs_a": len(diff["programs_a"]),
            "programs_b": len(diff["programs_b"]),
            "diff_lines": diff["changed"][0]["diff"][:6] if diff["changed"] else []}


ACTIONS = {
    "project_new": project_new,
    "project_new_cpu": project_new_cpu,
    "program_roundtrip_cpu": program_roundtrip_cpu,
    "project_save": project_save,
    "project_meta": project_meta,
    "program_paste_st": program_paste_st,
    "program_read_st": program_read_st,
    "program_import_xml": program_import_xml,
    "program_import_fb": program_import_fb,
    "program_import_fb_instance": program_import_fb_instance,
    "program_import_fb_params": program_import_fb_params,
    "datatype_struct_array": datatype_struct_array,
    "xmlgen_manual_template": xmlgen_manual_template,
    "inspect_devices_cpu": inspect_devices_cpu,
    "program_multi_programs": program_multi_programs,
    "program_edit_existing": program_edit_existing,
    "datatype_import": datatype_import,
    "datatype_member_var": datatype_member_var,
    "datatype_custom_members": datatype_custom_members,
    "datatype_member_access": datatype_member_access,
    "inspect_source_map": inspect_source_map,
    "inspect_devices": inspect_devices,
    "inspect_mil": inspect_mil,
    "build_convert_all": build_convert_all,
    "build_program_check": build_program_check,
    "build_error_detail": build_error_detail,
    "build_error_messages": build_error_messages,
    "batch_projects": batch_projects,
    "inspect_programs": inspect_programs,
    "project_diff": project_diff_action,
    "label_import_xml": label_import_xml,
    "label_multi_type": label_multi_type,
    "build_locate_error_line": build_locate_error_line,
    "project_reopen": project_reopen,
    "batch_new_projects": batch_new_projects,
    "project_check": project_check,
    "project_new_language": project_new_language,
}
