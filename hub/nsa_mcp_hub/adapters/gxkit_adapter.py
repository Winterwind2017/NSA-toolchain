"""gxkit 适配器：GX Works3（三菱 PLC）离线工程自动化。

复用 gxkit 自己的 ``caps`` / ``judges`` / ``runner``；本文件只做翻译。
注意 gxkit 的执行模型是**每条能力一个干净会话**（会前台拉起 GX Works3），
所以一条能力的典型耗时是 10–40 s，且会抢焦点。
"""

from __future__ import annotations

import os
import sys
import time

from ..tools import Kit, ToolSpec, normalize

from . import capgen, capcuration

KIT_KEY = "gx"
KIT_NAME = "gxkit"
SRC = os.environ.get("GXKIT_SRC", r"D:\bililive\gxkit\src")
RUNS = os.environ.get("NSA_MCP_HUB_RUNS", r"D:\bililive\nsa-mcp-hub\_runs")


def _import():
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    from gxkit import caps as caps_mod
    from gxkit import judges, runner
    return caps_mod, judges, runner


def _cap_row(cap) -> dict:
    return {"id": cap.id, "family": cap.family, "level": cap.level,
            "title": cap.title, "params": dict(cap.params),
            "expect": dict(cap.expect), "license": cap.license}


def build_kit() -> Kit:
    caps_mod, judges, runner = _import()
    kit = Kit(key=KIT_KEY, name=KIT_NAME,
              version=getattr(__import__("gxkit"), "__version__", "0.0.0"),
              instructions=(
                  "gxkit：GX Works3 离线工程自动化（%d 条能力）。执行会**前台拉起 GX Works3**，"
                  "单条约 10–40 s 且会抢焦点；返回的 checks 是从工程文件读回的判据。"
                  % len(caps_mod.CAPS)))

    def status(_args: dict) -> dict:
        from gxkit import win
        exes = [n for n in ("GXW3.exe", "GX Works3.exe", "GT Designer3.exe")
                if any(p.name.lower() == n.lower() for p in _procs(win))]
        return normalize(KIT_KEY, "status", ok=True,
                         reads={"src": SRC, "cap_count": len(caps_mod.CAPS),
                                "families": sorted({c.family for c in caps_mod.CAPS}),
                                "running": exes})

    def _procs(win):
        try:
            return win.list_processes()          # 若该版本没这个函数，回退空表
        except Exception:                        # noqa: BLE001
            return []

    def list_caps(args: dict) -> dict:
        family = (args.get("family") or "").strip()
        rows = [_cap_row(c) for c in caps_mod.CAPS
                if not family or c.family == family or c.id.startswith(family)]
        return normalize(KIT_KEY, "list_caps", ok=True,
                         reads={"total": len(rows),
                                "families": sorted({c.family for c in caps_mod.CAPS}),
                                "caps": rows})

    def run_capability(args: dict) -> dict:
        ids = args.get("ids") or args.get("id") or []
        if isinstance(ids, str):
            ids = [x.strip() for x in ids.split(",") if x.strip()]
        if not ids:
            return normalize(KIT_KEY, "run_capability", ok=False,
                             errors=["需要 ids（能力 id 数组）或 id（单个）"])
        by_id = {c.id: c for c in caps_mod.CAPS}
        unknown = [i for i in ids if i not in by_id]
        if unknown:
            return normalize(KIT_KEY, "run_capability", ok=False,
                             errors=["未知能力：%s" % ", ".join(unknown)])

        workdir = args.get("workdir") or os.path.join(
            RUNS, "gx", time.strftime("%Y%m%d-%H%M%S"))
        keep = bool(args.get("keep", True))
        rows, checks, errors = [], [], []
        started = time.time()
        for cid in ids:
            res = runner.run(workdir, only=cid, keep=keep)
            for row in res.get("caps", []):
                if row["id"] != cid:
                    continue
                cap = by_id[cid]
                row_checks = []
                for key, want in cap.expect.items():
                    why = judges.check(key, (row.get("reads") or {}).get(key), want)
                    row_checks.append({"check": key,
                                       "got": (row.get("reads") or {}).get(key),
                                       "want": want, "ok": why is None,
                                       **({"why": why} if why else {})})
                checks.extend(row_checks)
                errors.extend(row.get("errors") or [])
                rows.append({"capability": cid, "ok": bool(row.get("ok")),
                             "seconds": row.get("seconds"),
                             "checks": row_checks,
                             "reads": row.get("reads") or {},
                             "errors": row.get("errors") or []})
        ok = bool(rows) and all(r["ok"] for r in rows)
        return normalize(KIT_KEY, "run_capability", ok=ok,
                         reads={"total": len(rows), "workdir": workdir},
                         checks=checks, errors=errors,
                         seconds=time.time() - started, results=rows)

    def selftest(_args: dict) -> dict:
        # gxkit.actions 会拉起 UI 依赖，宿主侧不能直接 import；按源码文本核对。
        actions_src = os.path.join(SRC, "gxkit", "actions.py")
        try:
            with open(actions_src, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            return normalize(KIT_KEY, "selftest", ok=False,
                             errors=["读不到 actions.py：%s" % exc])
        problems = []
        for cap in caps_mod.CAPS:
            # gxkit 的动作函数常带 _action 后缀（project_diff → project_diff_action），
            # 所以只核对它是否登记在 ACTIONS 表里。
            if ('"%s":' % cap.action) not in text:
                problems.append("%s 的动作 %r 没登记进 ACTIONS" % (cap.id, cap.action))
            if not cap.expect:
                problems.append("%s 没有判据" % cap.id)
        ids = [c.id for c in caps_mod.CAPS]
        if len(ids) != len(set(ids)):
            problems.append("cap id 有重复")
        return normalize(KIT_KEY, "selftest", ok=not problems,
                         reads={"cap_count": len(caps_mod.CAPS),
                                "actions_source": actions_src, "problems": problems},
                         errors=problems)

    kit.add(ToolSpec("gx_status", "gxkit 环境自检（不启动 GX Works3）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     status, timeout_s=60))
    kit.add(ToolSpec("gx_list_caps", "列出 gxkit 能力与判据。",
                     {"type": "object",
                      "properties": {"family": {"type": "string"}},
                      "additionalProperties": False},
                     list_caps, timeout_s=30))
    kit.add(ToolSpec("gx_run_capability",
                     "真机执行一条或多条能力（会前台拉起 GX Works3，单条 10–40 s，抢焦点）。",
                     {"type": "object",
                      "properties": {"ids": {"type": "array", "items": {"type": "string"}},
                                     "id": {"type": "string"},
                                     "workdir": {"type": "string"},
                                     "keep": {"type": "boolean",
                                              "description": "跑完是否保留 GX 窗口"},
                                     "request_id": {"type": "string",
                                                    "description": "幂等键"}},
                      "additionalProperties": False},
                     run_capability, timeout_s=600,
                     must_have_checks=True, idempotent=True))
    kit.add(ToolSpec("gx_selftest", "离线自检：动作与判据是否齐全（不需要 GX Works3）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     selftest, timeout_s=60))
    # ── P3：能力 → 任务级工具（策展清单见 capcuration.GX）──────────────
    def _call_cap(cap_id: str, params: dict) -> dict:
        by_id = {c.id: c for c in caps_mod.CAPS}
        cap = by_id.get(cap_id)
        if cap is None:
            return normalize(KIT_KEY, cap_id, ok=False, errors=["未知能力：%s" % cap_id])
        try:
            capgen.merge_params(getattr(cap, "params", None), params)
        except ValueError as exc:
            return normalize(KIT_KEY, cap_id, ok=False, errors=[str(exc)])
        # gxkit 的能力是**场景脚本**（params 基本为空），按 id 跑即可
        payload = run_capability({"ids": [cap_id]})
        payload["capability"] = cap_id
        return payload

    kit.tools.extend(capgen.build_tools(
        caps_mod.CAPS, prefix=KIT_KEY, call=_call_cap,
        only=None, timeout_s=600.0,
        note="由能力自动生成"))

    return kit
