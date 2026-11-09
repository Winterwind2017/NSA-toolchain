"""真机执行层：起 AutoCAD / 跑一条或一组能力 / 收尾。

CLI（`acadkit run` / `acadkit cap`）、MCP server 与 `tests/live_judges.py`
都走这里 —— 只此一条路径，避免"测试一套、CLI 一套"。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import caps
from .core import com, env, launch
from .judges.case import CaseRunner, env_signature, finish


class Watchdog:
    """单例超时看门狗。

    有些 AutoCAD 命令会停在提示符上等输入，`SendCommand` 永不返回。超时就
    **强杀 acad 并退出进程**（不是假装通过），把现场写进 `TIMEOUT.txt`。
    """

    def __init__(self, timeout_s: float, workdir: str):
        self.timeout_s = timeout_s
        self.workdir = workdir
        self.deadline = 0.0
        self.case_id: Optional[str] = None
        self._t: Optional[threading.Thread] = None

    def start(self) -> None:
        def loop() -> None:
            while True:
                time.sleep(1.0)
                if self.deadline and time.time() > self.deadline:
                    cid = self.case_id
                    msg = ("用例 %s 超过 %.0fs 未返回 —— 大概率停在 AutoCAD "
                           "命令提示符上。已强杀 acad.exe 并中止本轮。"
                           % (cid, self.timeout_s))
                    print("\n!! " + msg, flush=True)
                    try:
                        with open(os.path.join(self.workdir, "TIMEOUT.txt"), "w",
                                  encoding="utf-8") as fh:
                            fh.write(msg + "\n")
                    except Exception:                   # noqa: BLE001
                        pass
                    subprocess.run(["taskkill", "/F", "/IM", "acad.exe"],
                                   capture_output=True)
                    os._exit(9)

        self._t = threading.Thread(target=loop, daemon=True)
        self._t.start()

    def arm(self, case_id: str) -> None:
        self.case_id = case_id
        self.deadline = time.time() + self.timeout_s

    def disarm(self) -> None:
        self.deadline = 0.0


def _default_workdir(prefix: str) -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(root, "_scratch", "%s_%s" % (prefix, stamp))
    os.makedirs(path, exist_ok=True)
    return path




def run(cases: Sequence[Any], *, workdir: Optional[str] = None,
        case_timeout: float = 120.0, keep: bool = False,
        progress: Optional[Callable[[str], None]] = None,
        prefix: str = "run") -> Dict[str, Any]:
    """跑一组 `Case`，返回 results 载荷（不写文件）。"""
    say = progress or (lambda m: print(m))
    workdir = workdir or _default_workdir(prefix)
    os.makedirs(workdir, exist_ok=True)

    sig_before = env_signature()
    say("跑前环境指纹：%s" % sig_before)

    watch = Watchdog(case_timeout, workdir)
    watch.start()

    info = launch.launch()
    app = info["app"]
    launched = info["launched"]
    say("AutoCAD：%s（profile=%r，等待 %ss）"
        % ("本次启动" if launched else "附加到已运行实例",
           info.get("profile"), info.get("waited_s")))

    results: List[Dict[str, Any]] = []
    runner = None
    baseline = None
    finish_info: Dict[str, Any] = {}
    error: Optional[str] = None
    try:
        runner = CaseRunner(app, workdir, log=say)
        baseline = runner.ensure_baseline_doc()
        app = com.refresh(app)
        profile = launch.read_profile(app)
        say("活动文档 profile：%r" % (profile,))
        if profile is None or profile.strip() != env.REQUIRED_PROFILE:
            raise RuntimeError("拒绝在非 %s 配置下跑用例（实际 %r）"
                               % (env.REQUIRED_PROFILE, profile))
        for case in cases:
            say("\n>>> %s  %s" % (case.id, case.title))
            watch.arm(case.id)
            res = runner.run(case)
            watch.disarm()
            results.append(res)
            failed = [k for k, v in res["checks"].items() if v is False]
            say("    %s  %.1fs  %s"
                % ("PASS" if res["ok"] else "FAIL", res["duration_s"],
                   ("失败项：" + ", ".join(failed)) if failed else ""))
            for note in res.get("notes") or []:
                say("    note: %s" % note)
    except Exception as exc:                            # noqa: BLE001
        error = "%s: %s" % (type(exc).__name__, exc)
        say("!! 跑用例时异常退出：%s" % error)
        traceback.print_exc()
    finally:
        watch.disarm()
        try:
            if runner is not None and baseline is not None:
                finish_info = finish(app, baseline,
                                     quit_app=(launched and not keep))
                say("\n收尾：%s"
                    % json.dumps(finish_info, ensure_ascii=False, default=str))
        except Exception as exc:                        # noqa: BLE001
            say("!! 收尾失败：%s: %s" % (type(exc).__name__, exc))

    sig_after = env_signature()
    say("跑后环境指纹：%s" % sig_after)
    payload = {
        "tool": "acadkit",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "workdir": workdir,
        "autocad": {"launched": launched, "exe": info.get("exe"),
                    "profile": info.get("profile"),
                    "waited_s": info.get("waited_s")},
        "env_before": sig_before,
        "env_after": sig_after,
        "finish": finish_info,
        "error": error,
        "results": results,
        "ok": (error is None and bool(results)
               and all(r["ok"] for r in results)),
    }
    return payload


def run_one(cap_id: str, params: Optional[Dict[str, Any]] = None, **kw: Any
            ) -> Dict[str, Any]:
    cap = caps.get(cap_id)
    case = cap.case(params or {})
    payload = run([case], prefix="cap_%s" % cap_id.replace(".", "_"), **kw)
    payload["cap"] = {
        "id": cap.id, "family": cap.family, "title": cap.title,
        "level": cap.level,
        "params": {**cap.params, **(params or {})},
    }
    return payload


def summarize(payload: Dict[str, Any]) -> str:
    """给 CLI 打印的人读摘要。"""
    lines = []
    for r in payload.get("results") or []:
        failed = [k for k, v in (r.get("checks") or {}).items() if v is False]
        lines.append("%-28s %-6s %5.1fs %s"
                     % (r["id"], "PASS" if r["ok"] else "FAIL",
                        r.get("duration_s") or 0.0,
                        ", ".join(failed) if failed else ""))
    if not lines:
        lines.append("（没有跑任何用例）")
    return "\n".join(lines)
