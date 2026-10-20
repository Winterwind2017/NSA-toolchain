"""tests/test_live.py —— 把真机套件接进 pytest

每个套件是**独立子进程**（原因见 `run_all.py` 的说明），pytest 只负责编排与报告。

    pytest tests -q --live              # 全跑
    pytest tests -q --live -k drawing   # 只跑出图
    pytest tests -q                     # 全跳过（默认）

非真机的部分（registry 口径、marks 常量、CLI 结构）不在这里，见 `test_offline.py`。
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SUITES = ["selftest", "mcp_smoke", "live", "part", "sketch", "sketch_ops",
          "inspect", "asm_ops", "asm_state", "features", "io",
          "doc_ops", "drawing_extra", "drawing", "balloon"]


def _run(only: str, timeout: float) -> subprocess.CompletedProcess:
    cmd = [sys.executable, os.path.join(HERE, "run_all.py"), "--only", only,
           "--timeout", str(timeout)]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout + 120,
                          stdin=subprocess.DEVNULL, cwd=ROOT,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


@pytest.mark.live
@pytest.mark.parametrize("suite", SUITES)
def test_suite(suite: str, request: pytest.FixtureRequest) -> None:
    timeout = float(request.config.getoption("--live-timeout"))
    proc = _run(suite, timeout)
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-12:])
    assert proc.returncode == 0, "套件 %s 失败（rc=%s）\n%s\n%s" % (
        suite, proc.returncode, tail, (proc.stderr or "")[-400:])
