"""`acadkit status` —— 环境自检（只附加，不启动）。

判据（按 `docs/JUDGE_SPEC.md` 第三节）：

| 检查 | 期望 | 不通过的后果 |
|---|---|---|
| AutoCAD 是否运行 | 只报告，不算失败 | — |
| profile | `<<VANILLA>>` | **退出码 4**（会污染用户的 ACADE 配置） |
| 实例数 | 1 | 退出码 4（多实例会导致 COM 连错文档） |
| `.sv$` 残留 | = 基线 | 退出码 5（下次启动会弹"图形修复"） |
| 其它系统变量 | = 基线 | 退出码 5 |
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from . import __version__
from .core import com, env


def collect(compare_baseline: bool = True) -> Tuple[Dict[str, Any], int]:
    """采快照并判定。返回 (报告, 退出码)。"""
    app = com.attach_or_none()
    snap = env.snapshot(app)
    prof = env.profile_ok(snap)
    base = env.read_baseline() if compare_baseline else None
    drift = env.diff(base, snap) if base else {}

    checks: Dict[str, Any] = {
        "attached": snap["running"],
        "single_instance": snap["process_count"] == 1 if snap["running"] else None,
        "profile_ok": prof,
        "baseline_present": base is not None,
        "no_env_drift": (not drift) if base else None,
    }

    code = 0
    problems = []
    if prof is False:
        code = 4
        problems.append("profile 不是 %s（实际 %r）——拒绝在非 VANILLA 配置下执行建模"
                        % (env.REQUIRED_PROFILE,
                           (snap.get("variables") or {}).get("CPROFILE")))
    if snap["running"] and snap["process_count"] > 1:
        code = code or 4
        problems.append("检测到 %d 个 acad.exe，必须只保留 1 个（否则 COM 会连错文档）"
                        % snap["process_count"])
    if drift:
        code = code or 5
        problems.append("环境漂移：%s" % ", ".join(sorted(drift)))

    report = {
        "tool": "acadkit status",
        "version": __version__,
        "snapshot": snap,
        "checks": checks,
        "drift": drift,
        "problems": problems,
        "ok": code == 0,
    }
    return report, code


def _show(vars_: Dict[str, Any], key: str) -> str:
    """区分「读不到」与「读到空值」——环境漂移判据依赖这个区别。"""
    if key not in vars_:
        return "（读不到）"
    val = vars_.get(key)
    if val is None:
        return "（读不到）"
    return val if str(val).strip() else "（空）"

def render(report: Dict[str, Any]) -> str:
    s = report["snapshot"]
    v = s.get("variables") or {}
    lines = [
        "acadkit %s" % report["version"],
        "",
        "AutoCAD     : %s" % ("运行中 · v%s" % s.get("version") if s["running"]
                              else "未运行（只读命令不会启动它）"),
        "实例数      : %s" % s.get("process_count"),
        "文档数      : %s" % s.get("documents"),
        "profile     : %s" % (v.get("CPROFILE") or "（读不到：需要打开一个文档）"),
        "TRUSTEDPATHS: %s" % _show(v, "TRUSTEDPATHS"),
        "SECURELOAD  : %s" % _show(v, "SECURELOAD"),
        ".sv$ 残留   : %s" % s.get("sv_count"),
        "",
    ]
    c = report["checks"]
    def mark(x: Optional[bool]) -> str:
        return "SKIP" if x is None else ("OK" if x else "FAIL")
    baseline_mark = ("OK" if c["baseline_present"]
                     else "未采（跑 acadkit env-baseline）")
    lines += [
        "检查:",
        "  profile = <<VANILLA>>      %s" % mark(c["profile_ok"]),
        "  单实例                     %s" % mark(c["single_instance"]),
        "  环境基线                   %s" % baseline_mark,
        "  与基线一致                 %s" % mark(c["no_env_drift"]),
    ]
    hints = []
    if not s["running"]:
        hints.append("AutoCAD 未运行：只读命令不会启动它；要验 profile 请先打开 AutoCAD。")
    elif not s["documents"]:
        hints.append("AutoCAD 在运行但没有打开的文档：系统变量读不到（不要为读数去新建文档）。")
    if not c["baseline_present"]:
        hints.append("还没有环境基线：跑一次 `acadkit env-baseline` 再执行用例。")
    if hints:
        lines += ["", "提示:"] + ["  - " + h for h in hints]
    if report["drift"]:
        lines += ["", "漂移明细:"]
        for k, (a, b) in report["drift"].items():
            lines.append("  %-16s %r → %r" % (k, a, b))
    if report["problems"]:
        lines += ["", "问题:"]
        lines += ["  - " + p for p in report["problems"]]
    lines += ["", "结论: %s" % ("通过" if report["ok"] else "未通过")]
    return "\n".join(lines)
