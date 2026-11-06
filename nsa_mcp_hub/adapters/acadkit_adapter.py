from __future__ import annotations

import os
import sys

from ..contracts import require_present
from ..tools import Kit, ToolSpec, normalize

from . import capgen, capcuration

KIT_KEY = "acad"
KIT_NAME = "AutoCAD 2025"
SRC = os.environ.get("ACADKIT_SRC", os.path.expanduser(r"~\acadkit\src"))


def _import():
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    from acadkit import caps as caps_mod
    from acadkit import live, status
    # 预热 ezdxf：DXF 判据用的是它，而**首次 import 发生在工具调用线程里**
    # （stdout 被重定向、COM 已初始化、读线程在跑）时会卡死——实测卡 45 s+，
    # faulthandler 显示停在 ezdxf/lldxf/validator.py 的 import。启动时导入一次即可。
    try:
        import ezdxf  # noqa: F401  prewarm
    except Exception:                                  # noqa: BLE001
        pass
    return caps_mod, live, status


def build_kit() -> Kit:
    caps_mod, live, status_mod = _import()
    kit = Kit(key=KIT_KEY, name=KIT_NAME,
              version=getattr(__import__("acadkit"), "__version__", "0.0.0"),
              instructions=(
                  "acadkit：AutoCAD 2025 自动化内核（%d 条能力）。默认 keep=true 跑完不退出"
                  "现有 AutoCAD 会话；返回的 checks/detail 是几何判据。" % len(caps_mod.CAPS)))

    def status(_args: dict) -> dict:
        report, code = status_mod.collect(compare_baseline=True)
        return normalize(KIT_KEY, "status", ok=(code == 0),
                         reads={"exit_code": code, "report": report})

    def _row(cap) -> dict:
        return {"id": cap.id, "family": cap.family, "level": cap.level,
                "title": cap.title, "params": dict(cap.params or {}),
                # acadkit 的判据是**代码**（judge 可调用），不是声明式 expect 字典
                "expect": getattr(cap, "expect", "pass"),
                "expect_fail_checks": list(getattr(cap, "expect_fail_checks", ()) or ()),
                "negative": bool(getattr(cap, "is_negative", False)),
                "judge": getattr(getattr(cap, "judge", None), "__name__", "callable"),
                "wants_dxf": bool(getattr(cap, "wants_dxf", False))}

    def list_caps(args: dict) -> dict:
        family = (args.get("family") or "").strip()
        rows = [_row(c) for c in caps_mod.CAPS if not family or c.family == family]
        return normalize(KIT_KEY, "list_caps", ok=True,
                         reads={"total": len(rows),
                                "families": sorted(caps_mod.FAMILIES), "caps": rows})

    def run_capability(args: dict) -> dict:
        ids = args.get("ids") or args.get("id") or ""
        if isinstance(ids, list):
            ids = ",".join(ids)
        keys = [k.strip() for k in ids.split(",") if k.strip()] if ids else None
        cases = caps_mod.cases(keys)
        if not cases:
            return normalize(KIT_KEY, "run_capability", ok=False,
                             errors=["没有匹配的能力：%r" % (ids,)])
        params = args.get("params")
        if params:
            cases = [caps_mod.BY_ID[c.id].case(params) for c in cases]
        payload = live.run(cases, keep=bool(args.get("keep", True)),
                           case_timeout=float(args.get("case_timeout", 120.0)),
                           progress=lambda m: sys.stderr.write(m + "\n"),
                           prefix="nsa-mcp-hub")
        results = []
        for r in payload.get("results") or []:
            # acadkit 的判据是**代码**，返回的是人类可读的字符串条目；
            # 这里折成统一结构：文本放 check，ok 取该能力自身的判定。
            raw_checks = r.get("checks") or []
            norm_checks = []
            for item in raw_checks:
                if isinstance(item, dict):
                    norm_checks.append(item)
                else:
                    norm_checks.append({"check": str(item), "ok": bool(r["ok"])})
            results.append({"capability": r["id"], "ok": bool(r["ok"]),
                            "seconds": r.get("duration_s"),
                            "checks": norm_checks,
                            "detail": r.get("detail"),
                            "errors": r.get("notes") or []})
        checks = [c for r in results for c in (r["checks"] or [])]
        errors = [e for r in results for e in (r["errors"] or [])]
        # acadkit 的"读数"在 detail 里（handle/端点/长度/reopen 对照），
        # 统一放进 reads.details，避免调用方以为 checks 的 got=None 就是没读到。
        details = {r["capability"]: r["detail"] for r in results if r.get("detail")}
        return normalize(KIT_KEY, "run_capability", ok=bool(payload.get("ok")),
                         reads={"workdir": payload.get("workdir"),
                                "autocad": payload.get("autocad"),
                                "env_before": payload.get("env_before"),
                                "env_after": payload.get("env_after"),
                                "details": details},
                         checks=checks, errors=errors, results=results,
                         error=payload.get("error"))

    kit.add(ToolSpec("acad_status",
                     "AutoCAD 环境自检：profile/系统变量/文档数/进程/单实例（只附加，不启动）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     status, timeout_s=120))
    kit.add(ToolSpec("acad_list_caps", "列出 acadkit 能力（族/级别/参数/判据）。",
                     {"type": "object",
                      "properties": {"family": {"type": "string"}},
                      "additionalProperties": False},
                     list_caps, timeout_s=30))
    kit.add(ToolSpec("acad_run_capability",
                     "真机执行一条或多条能力；默认保留现有 AutoCAD 会话（keep=true）。",
                     {"type": "object",
                      "properties": {"ids": {"type": "array", "items": {"type": "string"}},
                                     "id": {"type": "string",
                                            "description": "族或 id，逗号分隔"},
                                     "params": {"type": "object"},
                                     "keep": {"type": "boolean"},
                                     "case_timeout": {"type": "number"},
                                     "request_id": {"type": "string",
                                                    "description": "幂等键"}},
                      "additionalProperties": False},
                     run_capability, timeout_s=900,
                     must_have_checks=True, idempotent=True))
    # ── P1：能力 → 任务级工具（策展清单见 capcuration.ACAD）──────────
    def _call_cap(cap_id: str, params: dict) -> dict:
        cap = next((c for c in caps_mod.CAPS if c.id == cap_id), None)
        if cap is None:
            return normalize(KIT_KEY, cap_id, ok=False, errors=["未知能力：%s" % cap_id])
        try:
            merged = capgen.merge_params(getattr(cap, "params", None), params)
        except ValueError as exc:
            return normalize(KIT_KEY, cap_id, ok=False, errors=[str(exc)])
        payload = run_capability({"ids": [cap_id], "params": merged})
        # 单能力工具：把 capability 字段换成工具指向的能力，便于回溯
        payload["capability"] = cap_id
        return payload

    kit.tools.extend(capgen.build_tools(
        caps_mod.CAPS, prefix=KIT_KEY, call=_call_cap,
        only=capcuration.ACAD, timeout_s=300.0,
        note="由能力自动生成"))

    return kit
