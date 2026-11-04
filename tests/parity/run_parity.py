#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""上游测试对照跑：把上游 4 个 kit 的测试套件在本机跑一遍，看 hub 有没有退化。

三组：

1. **hubsw**（hub 自带、从上游 vendored 的几何代码）
   `tests/parity/hubsw/` 里是上游 `MCP/Solidworks/tests` 的 6 个纯几何测试文件，
   只改了 import 前缀。这组直接验证 hub 的副本不缺料。
2. **EPLAN**（hub 直接代理的代码）
   上游 `MCP/EPLAN/tests` 里不依赖真机的 5 个：intent / native_snapshot /
   help_search / bridge / transport_windows。
3. **CATIA**（同样代理）
   上游 `MCP/CATIA/tests` 里不碰 COM 的 unittest 文件。

用法：
    python tests/parity/run_parity.py            # 全跑
    python tests/parity/run_parity.py --group sw # 只跑一组（sw|eplan|catia）
退出码：全部通过 0，否则 1。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent.parent
PARITY = HUB / "tests" / "parity"
UPSTREAM = Path(os.environ.get("CAD_AGENT_HUB", r"D:\bililive\CAD-Agent-Hub")) / "MCP"

EPLAN_TESTS = ["test_intent.py", "test_native_snapshot.py", "test_help_search.py",
               "test_bridge.py", "test_transport_windows.py"]
CATIA_TESTS = ["test_contracts.py", "test_compatibility.py", "test_surfaces.py",
               "test_runtime.py", "test_simulation.py", "test_modeling.py",
               "test_server_contract.py"]


def env_with(path: Path | None) -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    paths = [str(HUB)]
    if path is not None:
        paths.insert(0, str(path))
    env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    return env


def run(cmd: list[str], cwd: Path, env: dict) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def summarize(text: str) -> tuple[int, int]:
    """从 pytest / unittest 输出里抠出 (通过, 失败)。"""
    passed = failed = 0
    m = re.search(r"(\d+) passed", text)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", text)
    if m:
        failed = int(m.group(1))
    m = re.search(r"Ran (\d+) tests?", text)
    if m:
        total = int(m.group(1))
        if "OK" in text:
            passed = max(passed, total)
        else:
            failed = max(failed, total - passed)
    if "OK" in text and passed == 0:
        m = re.search(r"Ran (\d+)", text)
        passed = int(m.group(1)) if m else 0
    return passed, failed


def group_sw() -> tuple[int, int, str]:
    code, out = run([sys.executable, "-m", "unittest", "discover",
                     "-s", str(PARITY / "hubsw"), "-p", "test_*.py", "-v"],
                    cwd=HUB, env=env_with(None))
    passed, failed = summarize(out)
    return passed, failed, out


def group_pytest(tests_dir: Path, names: list[str], src: Path, label: str) -> tuple[int, int, str]:
    files = [str(tests_dir / name) for name in names if (tests_dir / name).is_file()]
    if not files:
        return 0, 0, "%s：找不到测试文件（%s）" % (label, tests_dir)
    code, out = run([sys.executable, "-m", "pytest", "-q", *files],
                    cwd=src, env=env_with(src))
    passed, failed = summarize(out)
    if code != 0 and failed == 0:
        failed = 1
    return passed, failed, out


def main() -> int:
    parser = argparse.ArgumentParser(description="上游测试对照跑")
    parser.add_argument("--group", default="all", choices=["all", "sw", "eplan", "catia"])
    args = parser.parse_args()

    groups: list[tuple[str, callable]] = []
    if args.group in ("all", "sw"):
        groups.append(("hubsw（hub vendored 几何）", group_sw))
    if args.group in ("all", "eplan"):
        groups.append(("EPLAN（离线 5 个套件）",
                       lambda: group_pytest(UPSTREAM / "EPLAN" / "tests", EPLAN_TESTS,
                                            UPSTREAM / "EPLAN", "EPLAN")))
    if args.group in ("all", "catia"):
        groups.append(("CATIA（非 COM 的 unittest）",
                       lambda: group_pytest(UPSTREAM / "CATIA" / "tests", CATIA_TESTS,
                                            UPSTREAM / "CATIA" / "src", "CATIA")))

    total_ok = total_fail = 0
    failed_groups = []
    for label, fn in groups:
        passed, failed, out = fn()
        total_ok += passed
        total_fail += failed
        print("\n=== %s：%d 通过 / %d 失败 ===" % (label, passed, failed))
        tail = [line for line in out.strip().splitlines() if line.strip()][-6:]
        for line in tail:
            print("   ", line[:150])
        if failed:
            failed_groups.append(label)

    print("\n" + "=" * 60)
    print("合计：%d 通过 / %d 失败" % (total_ok, total_fail))
    if failed_groups:
        print("失败的组：" + "、".join(failed_groups))
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
