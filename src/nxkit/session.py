"""起一个 `run_journal.exe` 会话、跑一批能力、收结果。"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

from . import protocol

DEFAULT_RUN_JOURNAL = r"D:\Program Files\Siemens\DesigncenterNX2512\NXBIN\run_journal.exe"
DEFAULT_BASE_DIR = r"D:\Program Files\Siemens\DesigncenterNX2512"


def run_journal_path() -> str:
    return os.environ.get("NXKIT_RUN_JOURNAL") or DEFAULT_RUN_JOURNAL


def code_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def runner_path() -> str:
    return os.path.join(code_root(), "nxkit", "runtime", "runner.py")


def available() -> tuple[bool, str]:
    rj = run_journal_path()
    if not os.path.isfile(rj):
        return False, "找不到 run_journal.exe：%s（设 NXKIT_RUN_JOURNAL）" % rj
    base = os.path.dirname(os.path.dirname(rj))
    if not os.path.isdir(base):
        return False, "安装目录不存在：%s" % base
    return True, rj


def _kill_tree(proc) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, timeout=20)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    for name in ("ugraf", "run_journal"):
        try:
            subprocess.run(["taskkill", "/IM", name + ".exe", "/F"],
                           capture_output=True, timeout=10)
        except Exception:
            pass


def run(job: dict, timeout: float = 600.0) -> dict:
    """执行 job；返回 {returncode, seconds, stdout, stderr, result, result_path}。"""
    ok, why = available()
    if not ok:
        raise RuntimeError(why)
    workdir = job["workdir"]
    os.makedirs(workdir, exist_ok=True)
    job_path = os.path.join(workdir, "job.json")
    protocol.write_json(job_path, job)

    env = dict(os.environ)
    env.setdefault("UGII_BASE_DIR", DEFAULT_BASE_DIR)
    env.setdefault("PYTHONIOENCODING", "utf-8")

    cmd = [run_journal_path(), runner_path(), "-nx", "-args", job_path]
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=workdir, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    try:
        out, err = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=30)
        except Exception:
            out, err = "", ""
    seconds = round(time.time() - t0, 2)

    result = None
    if os.path.isfile(job["result"]):
        try:
            result = protocol.read_json(job["result"])
        except Exception:
            result = None
    return {
        "returncode": proc.returncode,
        "seconds": seconds,
        "timed_out": timed_out,
        "stdout": out or "",
        "stderr": err or "",
        "result": result,
        "result_path": job["result"],
    }
