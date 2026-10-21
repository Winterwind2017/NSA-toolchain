"""显式启动 AutoCAD（并守住 profile）。

`core/com.py` 只附加不启动，这条规则不变；**需要启动是显式行为**，放在这里：

* 已在运行 → 直接返回（不抢用户实例）；
* 未运行 → `acad.exe /p "<<VANILLA>>"` 起一个，然后轮询 COM 直到能附加；
* 起来后立刻读 `CPROFILE`，不是 `<<VANILLA>>` 就干净退出并报错 ——
  绝不把用户配置改到 `<<ACADE>>` 里跑建模。

本机实测（2026-10-21）：不带 `/p` 直接起 acad.exe 会落到 `<<ACADE>>`；
带 `/p "<<VANILLA>>"` 起来后 `CPROFILE` 读回 `<<VANILLA>>`。
"""

from __future__ import annotations

import glob
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from . import com, env

_EXE_GLOBS = [
    r"C:\Program Files\Autodesk\AutoCAD 20*\acad.exe",
    r"D:\Program Files\Autodesk\AutoCAD 20*\acad.exe",
    r"C:\Program Files (x86)\Autodesk\AutoCAD 20*\acad.exe",
]

# Windows: 让 AutoCAD 不随本进程退出（本进程崩了也不带走用户的 CAD）
_DETACHED = 0x00000008


class LaunchError(RuntimeError):
    """启动失败 / profile 不合规。"""


def find_acad_exe() -> Optional[str]:
    explicit = os.environ.get("ACADKIT_ACAD_EXE")
    if explicit and os.path.isfile(explicit):
        return explicit
    found: List[str] = []
    for pattern in _EXE_GLOBS:
        found.extend(glob.glob(pattern))
    found = sorted(p for p in found if os.path.isfile(p))
    return found[-1] if found else None


def read_profile(app: Any) -> Optional[str]:
    """读 CPROFILE：应用级 → 活动文档 → 任一文档，都读不到才返回 None。

    `CPROFILE` 是文档级变量；刚建完文档时 ActiveDocument 代理可能还没就绪，
    所以这里要短重试（本机实测偶发一次读不到）。
    """
    for _ in range(4):
        for getter in (lambda: app.GetVariable("CPROFILE"),
                       lambda: app.ActiveDocument.GetVariable("CPROFILE")):
            try:
                return str(getter())
            except Exception:                           # noqa: BLE001
                continue
        try:
            docs = app.Documents
            for i in range(int(docs.Count)):
                try:
                    return str(docs.Item(i).GetVariable("CPROFILE"))
                except Exception:                       # noqa: BLE001
                    continue
        except Exception:                               # noqa: BLE001
            pass
        time.sleep(0.5)
    return None


def attach(wait_s: float = 180.0, poll_s: float = 2.0) -> Any:
    """等 AutoCAD 的 COM 变得可附加（已在运行则立刻返回）。"""
    deadline = time.time() + wait_s
    last: Optional[BaseException] = None
    while time.time() < deadline:
        try:
            return com.attach()
        except com.AcadNotRunning as exc:
            last = exc
            time.sleep(poll_s)
    raise LaunchError("等了 %.0fs 还是附加不上 AutoCAD（%s）" % (wait_s, last))


def launch(profile: str = env.REQUIRED_PROFILE, wait_s: float = 180.0,
           exe: Optional[str] = None, poll_s: float = 2.0) -> Dict[str, Any]:
    """确保有一个 VANILLA profile 的 AutoCAD 可附加。

    返回 `{"app", "launched", "exe", "profile", "waited_s", "pid"}`。

    注意：`CPROFILE` 是**文档级**变量，AutoCAD 没有打开文档时读不到（返回
    `None`）。所以刚启动时 `profile` 可能是 None —— 调用方打开文档后要再核
    一次（`tests/live_judges.py` 就是这么做的，不符就 rc=4 退出）。
    """
    existing = com.attach_or_none()
    if existing is not None:
        prof = read_profile(existing)
        if prof is not None and prof.strip() != profile:
            raise LaunchError("已在运行的 AutoCAD profile 是 %r，不是 %r；"
                              "拒绝在非 VANILLA 配置下执行建模" % (prof, profile))
        # 没有打开文档时读不到 CPROFILE（None）→ 交给调用方在开文档后再核
        return {"app": existing, "launched": False, "exe": None,
                "profile": prof, "waited_s": 0.0, "pid": None}

    exe = exe or find_acad_exe()
    if not exe or not os.path.isfile(exe):
        raise LaunchError("找不到 acad.exe（可用 ACADKIT_ACAD_EXE 指定）")

    t0 = time.time()
    proc = subprocess.Popen([exe, "/p", profile], close_fds=True,
                            creationflags=_DETACHED)
    app = attach(wait_s=wait_s, poll_s=poll_s)
    waited = round(time.time() - t0, 1)
    prof = read_profile(app)
    if prof is not None and prof.strip() != profile:
        result = com.clean_quit(app)
        raise LaunchError("启动后 CPROFILE=%r，不是 %r；已干净退出（%s）"
                          % (prof, profile, result))
    return {"app": app, "launched": True, "exe": exe, "profile": prof,
            "waited_s": waited, "pid": proc.pid}
