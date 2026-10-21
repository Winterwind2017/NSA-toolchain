"""一次 NX 会话跑一批能力，并逐条判据。"""

from __future__ import annotations

import os
import time

from . import caps, judges, protocol, session


def _workdir(workdir: str | None) -> str:
    if workdir:
        os.makedirs(workdir, exist_ok=True)
        return os.path.abspath(workdir)
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "_runs")
    return os.path.join(root, time.strftime("%Y%m%d-%H%M%S"))


def build_job(selected: list[caps.Cap], workdir: str) -> dict:
    entries = [{"id": c.id, "action": c.action, "params": dict(c.params)}
               for c in selected]
    return protocol.new_job(workdir, entries, session.code_root())


def run(selected: list[caps.Cap] | None = None, workdir: str | None = None,
        timeout: float = 900.0) -> dict:
    selected = selected or caps.list_caps()
    wd = _workdir(workdir)
    job = build_job(selected, wd)
    raw = session.run(job, timeout=timeout)
    result = raw.get("result") or {"caps": []}
    by_id = {r.get("id"): r for r in result.get("caps", [])}

    records = []
    for cap in selected:
        rec = by_id.get(cap.id)
        if rec is None:
            records.append({"id": cap.id, "ok": False, "checks": [],
                            "errors": ["没有结果（会话中断？）"], "seconds": None})
            continue
        records.append(judges.judge_record(cap, rec))
    passed = sum(1 for r in records if r["ok"])
    return {
        "workdir": wd,
        "session_seconds": raw["seconds"],
        "returncode": raw["returncode"],
        "timed_out": raw["timed_out"],
        "stdout_tail": (raw["stdout"] or "")[-800:],
        "stderr_tail": (raw["stderr"] or "")[-800:],
        "passed": passed,
        "total": len(records),
        "records": records,
    }


def summarize(res: dict) -> str:
    lines = ["%d/%d 通过  (会话 %.1fs, 退出码 %s)" % (
        res["passed"], res["total"], res["session_seconds"], res["returncode"])]
    for r in res["records"]:
        mark = "PASS" if r["ok"] else "FAIL"
        detail = ""
        if not r["ok"]:
            bad = [c for c in r["checks"] if not c["ok"]]
            if bad:
                detail = " | " + "; ".join(
                    "%s got=%r want=%r" % (c["check"], c["got"], c["want"])
                    for c in bad[:3])
            elif r["errors"]:
                detail = " | " + r["errors"][0].splitlines()[-1][:160]
        lines.append("  %-4s %-22s %s%s" % (mark, r["id"],
                                            ("%.2fs" % r["seconds"]) if r["seconds"] else "",
                                            detail))
    return "\n".join(lines)
