"""swkit._legacy.runner —— 把已验证的旧脚本作为"受管子进程"调用

为什么不是直接 import：
* 这些脚本本来是 CLI（`argparse` + `print` + `SystemExit`），就地 import 会把它们的
  输出吞进当前进程，还会污染 `sys.argv`；
* 它们在 `subprocess` 里跑，能天然加上**超时**与**隔离的 COM 初始化**；
* 已实测的调用方式就是这样（`sw_extra_mcp.py` 同款），换成进程内反而要重测。

两条硬规则（踩过）：

1. `stdin` 必须显式 `DEVNULL`。继承父进程的 stdin 管道会让子进程挂到超时。
2. 输出用 `capture_output` 收文本，不要往管道里灌二进制；编码统一 utf-8 + replace。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["SCRIPTS", "script_path", "run", "json_tail", "cache_dir"]

SCRIPTS = {
    "sim": "sw_sim.py",
    "motion": "sw_motion.py",
    "dm": "swdm_lite.py",
    "adv": "sw_adv.py",
    "ovba": "sw_ovba.py",
}


def cache_dir() -> str:
    """`~/.swkit`（缓存库、临时输出都放这里，不写进安装包目录）。"""
    path = os.environ.get("SWKIT_HOME") or os.path.join(os.path.expanduser("~"), ".swkit")
    os.makedirs(path, exist_ok=True)
    return path


def script_path(key: str) -> str:
    if key not in SCRIPTS:
        raise KeyError("未知 legacy 脚本：%s（可选 %s）" % (key, sorted(SCRIPTS)))
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), SCRIPTS[key])


def run(key: str, args: Sequence[str], timeout: float = 900.0,
        python: Optional[str] = None, cwd: Optional[str] = None) -> Dict[str, Any]:
    """跑一个 legacy 脚本，返回 `{ok, returncode, stdout, stderr, elapsed_s}`。"""
    exe = python or sys.executable
    cmd: List[str] = [exe, script_path(key)] + [str(a) for a in args]
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    started = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
            cwd=cwd or cache_dir(), env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -9, "stdout": "", "stderr": "",
                "elapsed_s": round(time.time() - started, 1),
                "error": "超时（%.0fs）" % timeout}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "elapsed_s": round(time.time() - started, 1),
    }


def json_tail(text: str, max_tries: int = 60) -> Optional[Any]:
    """从"散文 + JSON"的混合输出里取出最后一个可解析的 JSON 值。

    旧脚本常把诊断打印和结果 JSON 混在一起，这里从后往前找起点尝试解析。
    """
    if not text:
        return None
    text = text.strip()
    positions = [i for i, ch in enumerate(text) if ch in "{["]
    for pos in reversed(positions[-max_tries:]):
        try:
            return json.loads(text[pos:])
        except Exception:
            continue
    return None


def tail_lines(text: str, n: int = 12) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(lines[-n:])
