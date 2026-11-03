"""nxkit 适配器：把 146 条能力包装成 MCP 工具，判据原样回传。

执行链完全复用 nxkit 自己的东西：
``caps.CAPS`` → ``live.run()``（内部起 run_journal） → ``judges`` → 归一化。
本文件不实现任何建模逻辑。
"""

from __future__ import annotations

import os
import sys

from ..tools import Kit, ToolSpec, normalize

from . import capgen, capcuration

KIT_KEY = "nx"
KIT_NAME = "nxkit"
SRC = os.environ.get("NXKIT_SRC", r"D:\bililive\nxkit\src")


def _import():
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    from nxkit import caps as caps_mod          # noqa: F401
    from nxkit import judges, live, session    # noqa: F401
    return caps_mod, judges, live, session


def _cap_row(cap) -> dict:
    return {
        "id": cap.id,
        "family": cap.family,
        "level": cap.level,
        "title": cap.title,
        "params": dict(cap.params),
        "expect": dict(cap.expect),
        "reopen": cap.reopen,
        "license": cap.license,
    }


def build_kit() -> Kit:
    caps_mod, judges, live, session = _import()
    kit = Kit(
        key=KIT_KEY,
        name=KIT_NAME,
        version=getattr(__import__("nxkit"), "__version__", "0.0.0"),
        instructions=(
            "nxkit：UG NX 2512 自动化内核（%d 条能力）。先调 nx_list_caps 看有哪些能力与判据，"
            "再用 nx_run_capability 真机执行；返回里 checks 是判据逐项比对结果，"
            "ok 只由 checks 决定——不要只看是否抛异常。"
            % len(caps_mod.CAPS)),
    )

    def status(_args: dict) -> dict:
        ok, why = session.available()
        return normalize(
            KIT_KEY, "status", ok=ok,
            reads={
                "run_journal": session.run_journal_path(),
                "code_root": session.code_root(),
                "cap_count": len(caps_mod.CAPS),
                "families": list(caps_mod.FAMILIES),
                "nx_base_dir": os.environ.get("UGII_BASE_DIR"),
            },
            errors=[] if ok else [why],
        )

    def list_caps(args: dict) -> dict:
        family = (args.get("family") or "").strip()
        rows = [_cap_row(c) for c in caps_mod.list_caps(family or None)]
        return normalize(KIT_KEY, "list_caps", ok=True,
                         reads={"total": len(rows), "families": list(caps_mod.FAMILIES),
                                "caps": rows})

    def run_capability(args: dict) -> dict:
        raw_ids = args.get("ids") or args.get("id") or []
        if isinstance(raw_ids, str):
            raw_ids = [x.strip() for x in raw_ids.split(",") if x.strip()]
        if not raw_ids:
            return normalize(KIT_KEY, "run_capability", ok=False,
                             errors=["需要 ids（能力 id 数组）或 id（单个）"])
        try:
            selected = [caps_mod.get(cid) for cid in raw_ids]
        except KeyError as exc:
            return normalize(KIT_KEY, "run_capability", ok=False,
                             errors=[str(exc)])

        timeout = float(args.get("timeout_s") or 900.0)
        result = live.run(selected, workdir=args.get("workdir"), timeout=timeout)

        records = []
        for rec in result.get("records", []):
            records.append({
                "capability": rec["id"],
                "ok": bool(rec["ok"]),
                "checks": rec.get("checks") or [],
                "errors": [e.splitlines()[-1][:400] if isinstance(e, str) else e
                           for e in (rec.get("errors") or [])],
                "seconds": rec.get("seconds"),
            })
        ok = (result.get("passed", 0) == result.get("total", 0)
              and result.get("total", 0) > 0
              and not result.get("timed_out"))
        # 注意：run_journal 正常结束也会往 stderr 打 "Journal execution results…"
        # 且常带 returncode=1，所以 stderr/returncode 只作为诊断，**不参与 ok 判定**。
        return normalize(KIT_KEY, "run_capability", ok=ok,
                         reads={"passed": result.get("passed"),
                                "total": result.get("total"),
                                "workdir": result.get("workdir"),
                                "session_seconds": result.get("session_seconds"),
                                "returncode": result.get("returncode"),
                                "timed_out": result.get("timed_out")},
                         checks=[c for r in records for c in r["checks"]],
                         errors=[e for r in records for e in r["errors"]],
                         seconds=result.get("session_seconds"),
                         results=records,
                         stderr_tail=result.get("stderr_tail"))

    def selftest(_args: dict) -> dict:
        # actions.py 顶部 `import NXOpen`，只能在 NX 进程内导入；
        # 所以这里和 nxkit 自己的 cli 一样按源码文本核对动作是否实现。
        actions_src = os.path.join(session.code_root(), "nxkit", "runtime", "actions.py")
        try:
            with open(actions_src, encoding="utf-8") as fh:
                actions_text = fh.read()
        except OSError as exc:
            return normalize(KIT_KEY, "selftest", ok=False,
                             errors=["读不到 actions.py：%s" % exc])
        problems = []
        for cap in caps_mod.CAPS:
            if ("def %s(" % cap.action) not in actions_text:
                problems.append("%s 的动作 %r 未实现" % (cap.id, cap.action))
            if ('"%s": %s,' % (cap.action, cap.action)) not in actions_text:
                problems.append("%s 的动作 %r 没登记进 ACTIONS" % (cap.id, cap.action))
            if not cap.expect:
                problems.append("%s 没有判据" % cap.id)
        ids = [c.id for c in caps_mod.CAPS]
        if len(ids) != len(set(ids)):
            problems.append("cap id 有重复")
        return normalize(KIT_KEY, "selftest", ok=not problems,
                         reads={"cap_count": len(caps_mod.CAPS),
                                "actions_source": actions_src,
                                "problems": problems},
                         errors=problems)

    kit.add(ToolSpec("nx_status", "nxkit 环境自检：run_journal 是否可用、能力数、族。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     status, timeout_s=60))
    kit.add(ToolSpec("nx_list_caps",
                     "列出 nxkit 能力（id/族/级别/标题/默认参数/判据）。",
                     {"type": "object",
                      "properties": {"family": {"type": "string",
                                                "description": "只列某个族，如 solid/drawing"}},
                      "additionalProperties": False},
                     list_caps, timeout_s=30))
    kit.add(ToolSpec("nx_run_capability",
                     "真机执行一条或多条能力（起 run_journal 会话），返回 checks 判据与 reads。",
                     {"type": "object",
                      "properties": {
                          "ids": {"type": "array", "items": {"type": "string"},
                                  "description": "能力 id 列表，如 [\"solid.block\"]"},
                          "id": {"type": "string", "description": "单个能力 id（ids 的简写）"},
                          "timeout_s": {"type": "number", "description": "会话超时，默认 900"},
                          "workdir": {"type": "string", "description": "产物目录（可选）"},
                          "request_id": {"type": "string",
                                         "description": "幂等键：同 id 重试直接回放上次结果"}},
                      "additionalProperties": False},
                     run_capability, timeout_s=960,
                     must_have_checks=True, idempotent=True))
    kit.add(ToolSpec("nx_selftest",
                     "离线自检：每条能力的动作是否实现、判据是否齐全（不需要 NX）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     selftest, timeout_s=60))
    # ── P2：能力 → 任务级工具（策展清单见 capcuration.NX）──────────────
    import dataclasses

    def _call_cap(cap_id: str, params: dict) -> dict:
        try:
            cap = caps_mod.get(cap_id)
        except KeyError:
            return normalize(KIT_KEY, cap_id, ok=False, errors=["未知能力：%s" % cap_id])
        try:
            merged = capgen.merge_params(getattr(cap, "params", None), params)
        except ValueError as exc:
            return normalize(KIT_KEY, cap_id, ok=False, errors=[str(exc)])
        # nxkit 的 Cap 是 dataclass：换掉 params 就等于换掉这一条能力的输入
        try:
            selected = [dataclasses.replace(cap, params=merged)]
        except Exception:                           # noqa: BLE001
            selected = [cap]
        result = live.run(selected, timeout=900.0)
        records = []
        for rec in result.get("records", []):
            records.append({
                "capability": rec["id"],
                "ok": bool(rec["ok"]),
                "checks": rec.get("checks") or [],
                "errors": [e.splitlines()[-1][:400] if isinstance(e, str) else e
                           for e in (rec.get("errors") or [])],
                "seconds": rec.get("seconds"),
            })
        ok = (result.get("passed", 0) == result.get("total", 0)
              and result.get("total", 0) > 0
              and not result.get("timed_out"))
        return normalize(KIT_KEY, cap_id, ok=ok,
                         reads={"passed": result.get("passed"),
                                "total": result.get("total"),
                                "workdir": result.get("workdir"),
                                "session_seconds": result.get("session_seconds"),
                                "params": merged},
                         checks=[c for r in records for c in r["checks"]],
                         errors=[e for r in records for e in r["errors"]],
                         seconds=result.get("session_seconds"),
                         results=records)

    kit.tools.extend(capgen.build_tools(
        caps_mod.CAPS, prefix=KIT_KEY, call=_call_cap,
        only=capcuration.NX, timeout_s=900.0,
        note="由能力自动生成"))

    return kit
