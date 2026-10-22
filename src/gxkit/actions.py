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
    s = _boot(ctx)
    s.new_project(**NEW)
    saved = s.save_as(ctx["project"])
    return s, saved


def project_new(ctx: dict) -> dict:
    s = _boot(ctx)
    proj = s.new_project(**NEW)
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
    s.paste_st(ctx.get("code") or ST_CODE)
    s.convert_all()
    prog = read_progress(ctx["project"])
    return {"steps": s.steps(), "convert_errors": prog.get("errors"),
            "title": s.title()}


def build_convert_all(ctx: dict) -> dict:
    s, _ = _new_and_save(ctx)
    s.paste_st(ctx.get("code") or ST_CODE)
    s.convert_all()
    s.save()
    prog = read_progress(ctx["project"])
    return {"errors": prog.get("errors"), "warnings": prog.get("warnings"),
            "stages": len(prog.get("stages") or []), "found": prog.get("found")}


def build_program_check(ctx: dict) -> dict:
    """已转换工程 → 工具·程序检查 → 执行 → 读判定文本。"""
    s, _ = _new_and_save(ctx)
    s.paste_st(ctx.get("code") or ST_CODE)
    s.convert_all()
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
    再贴坏代码；保存后若 `Progress.txt` 还没更新，就再转换/保存一轮。
    """
    s, _ = _new_and_save(ctx)
    s.paste_st(ST_CODE)
    s.convert_all()
    good_steps = s.steps()

    s.paste_st(ctx.get("code") or BAD_ST_CODE)
    s.convert_all()
    s.save()

    prog = read_progress(ctx["project"])
    if prog.get("errors") is None:
        s.convert_all()
        s.save()
        prog = read_progress(ctx["project"])

    failed = prog.get("failed_stages") or []
    return {"errors": prog.get("errors"), "warnings": prog.get("warnings"),
            "failed_stage_count": len(failed),
            "failed_stage": failed[0] if failed else None,
            "stages": len(prog.get("stages") or []),
            "good_steps": good_steps,
            "progress_found": prog.get("found")}


def batch_projects(ctx: dict) -> dict:
    """同一会话里连做 N 个工程（粘贴不同参数 → 转换 → 菜单另存为）。"""
    count = int(ctx.get("batch_count") or 3)
    s = _boot(ctx)
    s.new_project(**NEW)
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
    clean = [x for x in items if x["exists"] and x["errors"] == 0]
    return {"items": len(items), "clean_items": len(clean),
            "seconds": round(time.time() - t0, 1),
            "distinct_sizes": len({x["bytes"] for x in items})}


def project_reopen(ctx: dict) -> dict:
    s, _ = _new_and_save(ctx)
    s.paste_st(ctx.get("code") or ST_CODE)
    s.convert_all()
    s.save()
    before = s.steps()
    s.close()
    time.sleep(2)
    s2 = _boot(ctx, project=ctx["project"])
    title = s2.title() or ""
    return {"reopened": pathlib.Path(ctx["project"]).name in title,
            "steps_before": before, "steps": s2.steps(), "title": title}


ACTIONS = {
    "project_new": project_new,
    "project_save": project_save,
    "project_meta": project_meta,
    "program_paste_st": program_paste_st,
    "build_convert_all": build_convert_all,
    "build_program_check": build_program_check,
    "build_error_detail": build_error_detail,
    "batch_projects": batch_projects,
    "project_reopen": project_reopen,
}
