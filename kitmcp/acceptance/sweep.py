"""能力扫描验收（P6）：把**每一条能力**当成一条用例跑一遍。

为什么需要：固定用例只有 39 条，而六个 kit 合计 285 条能力/命令。手写用例跟不上，
但每条能力**自带 judge**，所以可以机械地把"能力 → 用例"生成出来，用它的 judge 判定。

    python -m kitmcp.acceptance --kit acad --sweep            # 跑 acad 全部能力
    python -m kitmcp.acceptance --kit nx --sweep --sweep-max 20

注意：
* 负例能力（期望失败）默认跳过——它们的 judge 语义是"应该报错"，混在正常用例里会误判；
* codesys 只扫**无必填参数**的命令（其余需要真实路径/文本，交给固定用例）；
* 单个 kit 全扫很慢（nx 146 条 × ~15 s），所以有 `--sweep-max` 兜底。
"""

from __future__ import annotations

import importlib
from typing import Dict, List

from ..adapters import capgen, capcuration, codesys_tools

MODULES = {"sw": "swkit_adapter", "acad": "acadkit_adapter", "nx": "nxkit_adapter",
           "gx": "gxkit_adapter", "codesys": "codesyskit_adapter",
           "autoshop": "autoshopkit_adapter"}

# 各 kit 单条能力的典型耗时（秒），用来给用例设超时
# 单条用例上限（秒）；KITMCP_SWEEP_TIMEOUT=900 可整体放大（GX 的 FB/梯形图用例
# 实测 400 s 不够，冷启动 + 前台 UI 自动化）。
TIMEOUT = {"acad": 180, "nx": 300, "gx": 900, "codesys": 180, "sw": 300, "autoshop": 240}

import os as _os


def _timeout_for(kit_key: str) -> float:
    """单条扫描用例的上限（秒），支持 KITMCP_SWEEP_TIMEOUT 覆盖。"""
    base = float(TIMEOUT.get(kit_key, 300))
    try:
        return float(_os.environ.get("KITMCP_SWEEP_TIMEOUT") or base)
    except ValueError:
        return base


def _kit(kit_key: str):
    return importlib.import_module("kitmcp.adapters." + MODULES[kit_key]).build_kit()


def _caps_of(kit_key: str) -> List[dict]:
    kit = _kit(kit_key)
    lister = next((t for t in kit.tools if t.name.endswith("list_caps")), None)
    if lister is None:
        return []
    rows = (lister.handler({}) or {}).get("reads", {}).get("caps") or []
    return list(rows)


def sweep_cases(kit_key: str, limit: int = 0) -> List[dict]:
    """生成"一能力一用例"的清单。"""
    if kit_key == "codesys":
        # 先开一个临时工程：绝大多数命令是**有状态**的（E_STATE: no project is open），
        # 不建工程直接扫会得到一堆假 FAIL（实测 6/22）。
        import os
        import time
        proj = os.path.join(os.environ.get("TEMP", "."),
                            "kitmcp_sweep_codesys_%s.project" % time.strftime("%H%M%S"))
        cases = [{"id": "codesys.cap.project.create", "tool": "codesys_project_create",
                  "args": {"path": proj, "device": "CODESYS Control Win V3"},
                  "expect_ok": True, "timeout_s": 300}]
        for cmd, (_desc, params, _writes) in codesys_tools.S.items():
            if cmd in codesys_tools.SKIP:
                continue
            if codesys_tools.REQUIRED.get(cmd):
                continue                            # 需要真实输入的留给固定用例
            if cmd in ("project.close",):
                continue                            # 会把工程关掉，后续全报 E_STATE
            # 这些需要**真实设备/网关/父对象**，本机没有：
            #   online.*  → "网关没有正确配置"，login 必然失败
            #   symbols.create → "父对象不接受符号配置对象"（工程里没有 PLC 设备树）
            # 它们的能力判据本身没问题，是环境不满足，扫描里跳过（固定用例有专门覆盖）。
            if cmd.startswith("online.") or cmd == "symbols.create":
                continue
            cases.append({"id": "codesys.cap.%s" % cmd,
                          "tool": "codesys_" + cmd.replace(".", "_").replace("-", "_"),
                          "args": {}, "expect_ok": True,
                          "timeout_s": _timeout_for("codesys")})
        # 收尾：关掉扫描期间开的工程，否则下一次 codesys.create 会报
        # "A primary project is already open"（实测踩到）。
        cases.append({"id": "codesys.cap.project.close",
                      "tool": "codesys_project_close", "args": {},
                      "expect_ok": True, "timeout_s": 120})
        return cases[:limit] if limit else cases

    if kit_key == "autoshop":
        return []                                   # autoshop 不是能力表模型，跳过

    kit = _kit(kit_key)
    tool_names = {t.name for t in kit.tools}
    cases: List[dict] = []
    for row in _caps_of(kit_key):
        cap_id = str(row.get("id") or "")
        if not cap_id or row.get("negative"):
            continue
        name = capgen.tool_name(kit_key, cap_id)
        if name in tool_names:
            tool, cargs = name, {}
        else:
            # 没进策展清单的能力：走调度器（能力本身照样被 judge 验，只是没有专属工具）
            tool, cargs = "%s_run_capability" % kit_key, {"ids": [cap_id]}
        cases.append({"id": "%s.cap.%s" % (kit_key, cap_id), "tool": tool,
                      "args": cargs, "expect_ok": True,
                      "timeout_s": _timeout_for(kit_key)})
    return cases[:limit] if limit else cases


def coverage(kit_key: str) -> Dict[str, int]:
    """能力数 / 有工具的 / 被固定用例覆盖的（粗糙但够用）。"""
    from .cases import KITS
    spec_cases = KITS[kit_key]["cases"]
    covered_tools = {c.get("tool") for c in spec_cases}
    if kit_key == "codesys":
        total = len(codesys_tools.S)
        tools = len({t for t in covered_tools if t})
        return {"caps": total, "with_tool": len([c for c in codesys_tools.S
                                                 if c not in codesys_tools.SKIP]),
                "in_fixed_cases": tools}
    rows = _caps_of(kit_key)
    kit = _kit(kit_key)
    names = {t.name for t in kit.tools}
    with_tool = [r["id"] for r in rows
                 if capgen.tool_name(kit_key, str(r.get("id") or "")) in names]
    return {"caps": len(rows), "with_tool": len(with_tool),
            "in_fixed_cases": len(covered_tools & names)}
