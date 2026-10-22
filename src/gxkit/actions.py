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
    "project_reopen": project_reopen,
}
