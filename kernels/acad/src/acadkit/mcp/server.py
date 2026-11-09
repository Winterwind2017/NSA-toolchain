"""acadkit MCP server（stdio）。

    acadkit-mcp                 # 默认 stdio
    python -m acadkit.mcp.server

四个工具，都是**同一条路径**（`acadkit.live`）驱动，和 CLI / 测试完全一致：

| 工具 | 作用 |
|---|---|
| `acadkit_status` | 环境自检（只附加，不启动 AutoCAD） |
| `acadkit_list_caps` | 能力清单（族 / 级别 / registry 状态 / 默认参数） |
| `acadkit_registry` | 能力登记表（verified/usable_unjudged/pending/dead） |
| `acadkit_run_caps` | 跑一条或一组能力，返回 checks/detail/raw 证据 |

设计约束：**MCP 不额外发明能力**。每个工具最终都落到 `caps` 里的
"动作 + 判据"，返回值里带 `ok`（只由 `all(checks)` 算出）和可人工核对的
`detail`，与真机测试的 JSON 完全同构。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Optional

from .. import __version__, caps, registry, status


def _status_payload() -> Dict[str, Any]:
    report, code = status.collect(compare_baseline=True)
    return {"exit_code": code, "report": report}


def _list_caps(family: str = "") -> Dict[str, Any]:
    data = registry.load()
    by_id = {c["id"]: c for c in data["capabilities"]}
    rows = []
    for cap in caps.CAPS:
        if family and cap.family != family:
            continue
        rows.append({
            "id": cap.id, "family": cap.family, "level": cap.level,
            "title": cap.title, "negative": cap.is_negative,
            "registry_status": (by_id.get(cap.id) or {}).get("status"),
            "params": cap.params,
        })
    return {"total": len(rows), "families": sorted(caps.FAMILIES), "caps": rows}


def _run_caps(only: str = "", params: Optional[Dict[str, Any]] = None,
              keep: bool = True, case_timeout: float = 120.0) -> Dict[str, Any]:
    from .. import live

    keys = [k.strip() for k in only.split(",") if k.strip()] if only else None
    cases = caps.cases(keys)
    if not cases:
        return {"ok": False, "error": "没有匹配的能力：%r" % (only,)}
    if params:
        cases = [caps.BY_ID[c.id].case(params) for c in cases]
    payload = live.run(cases, keep=keep, case_timeout=case_timeout,
                       progress=lambda m: sys.stderr.write(m + "\n"),
                       prefix="mcp")
    compact = {
        "ok": payload["ok"],
        "error": payload.get("error"),
        "workdir": payload.get("workdir"),
        "autocad": payload.get("autocad"),
        "env_before": payload.get("env_before"),
        "env_after": payload.get("env_after"),
        "results": [{"id": r["id"], "ok": r["ok"],
                     "duration_s": r.get("duration_s"),
                     "checks": r.get("checks"),
                     "detail": r.get("detail"),
                     "notes": r.get("notes")}
                    for r in payload.get("results") or []],
    }
    return compact


def build_server():
    """构造 FastMCP server（导入失败时给出可执行的修法）。"""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:                            # noqa: BLE001
        raise SystemExit(
            "需要 mcp 包：pip install 'acadkit[mcp]'（原始错误：%s）" % exc)

    mcp = FastMCP(
        "acadkit",
        instructions=("AutoCAD 自动化内核 %s：能力清单 / 环境自检 / 真机跑判据。"
                      "每条能力的返回值都带 checks/detail，ok 只由 all(checks) 算出。"
                      % __version__))

    @mcp.tool()
    def acadkit_status() -> Dict[str, Any]:
        """环境自检：profile/系统变量/文档数/.sv$/进程/单实例（只附加，不启动）。"""
        return _status_payload()

    @mcp.tool()
    def acadkit_list_caps(family: str = "") -> Dict[str, Any]:
        """列出可实现能力（族 / 级别 / registry 状态 / 默认参数）。"""
        return _list_caps(family)

    @mcp.tool()
    def acadkit_registry(status: str = "") -> Dict[str, Any]:
        """能力登记表（可选 status=verified/usable_unjudged/pending/dead）。"""
        data = registry.load()
        rows = data["capabilities"]
        if status:
            rows = [c for c in rows if c.get("status") == status]
        return {"counts": registry.counts(data),
                "problems": registry.validate(data), "rows": rows}

    @mcp.tool()
    def acadkit_run_caps(only: str = "",
                         params: Optional[Dict[str, Any]] = None,
                         keep: bool = True,
                         case_timeout: float = 120.0) -> Dict[str, Any]:
        """跑一条或一组能力（只填族或 id，逗号分隔；空 = 全部）。

        返回每条能力的 checks/detail/raw；`ok` 只由 `all(checks)` 算出。
        `keep=True` 时跑完不退出 AutoCAD（默认保留用户的会话）。
        """
        return _run_caps(only=only, params=params, keep=keep,
                         case_timeout=case_timeout)

    return mcp


def main(argv: Optional[list] = None) -> int:
    mcp = build_server()
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
