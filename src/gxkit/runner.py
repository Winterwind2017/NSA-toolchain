"""跑能力：每条能力一个干净会话（启动 ~10 s，换来没有状态漂移）。"""

from __future__ import annotations

import json
import pathlib
import time
import traceback

from . import caps as caps_mod
from .actions import ACTIONS
from .judges import judge


def run(workdir: str | pathlib.Path, only: str | None = None,
        code: str | None = None, keep: bool = False) -> dict:
    wd = pathlib.Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    sel = [c for c in caps_mod.CAPS
           if not only or c.id.startswith(only) or c.family == only]

    rows = []
    t_all = time.time()
    for cap in sel:
        project = str(wd / ("%s.gx3" % cap.id.replace(".", "_")))
        ctx = {"workdir": wd, "project": project, "code": code, "session": None}
        t0 = time.time()
        err: list[str] = []
        reads: dict = {}
        try:
            reads = ACTIONS[cap.action](ctx) or {}
        except Exception:
            err.append(traceback.format_exc(limit=4).splitlines()[-1])
        fails = judge(cap.expect, reads)
        sess = ctx.get("session")
        if sess is not None and not keep:
            try:
                sess.close()
            except Exception:
                pass
        dt = round(time.time() - t0, 1)
        ok = not err and not fails
        rows.append({"id": cap.id, "family": cap.family, "level": cap.level,
                     "ok": ok, "seconds": dt, "reads": reads,
                     "errors": err + fails})
        print("  %s %-22s %6.1fs | %s"
              % ("PASS" if ok else "FAIL", cap.id, dt,
                 "；".join(err + fails)[:170] or "-"))

    passed = sum(1 for r in rows if r["ok"])
    dur = round(time.time() - t_all, 1)
    result = {"total": len(rows), "passed": passed, "seconds": dur,
              "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "caps": rows}
    (wd / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    print("%d/%d 通过  (会话 %.1fs)" % (passed, len(rows), dur))
    return result
