"""环境快照与比对：profile / 系统变量 / 进程 / .sv$ 残留。

为什么单独一层：swkit 最坏情况是"模型没变"；acadkit 最坏情况是
**"模型变了，本机 AutoCAD 配置也被改坏"**。历史上真的发生过：
profile 落到 `<<ACADE>>`、`TRUSTEDPATHS` 残留、`Stop-Process -Force`
留下 `.sv$` 导致每次启动弹"图形修复"。

所以每个用例前后各做一次快照，不一致即判失败。
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import time
from typing import Any, Dict, Optional

# 必须与基线一致的键（少一个都不行）
TRACKED_VARS = ("CPROFILE", "TRUSTEDPATHS", "SECURELOAD", "MEASUREMENT",
                "INSUNITS", "FILEDIA", "CMDDIA")

REQUIRED_PROFILE = "<<VANILLA>>"


def _proc_count(name: str = "acad") -> int:
    """用 tasklist 数进程（避免额外依赖 psutil）。"""
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s.exe" % name],
                             capture_output=True, text=True, timeout=10,
                             encoding="utf-8", errors="replace")
        return sum(1 for line in out.stdout.splitlines()
                   if line.lower().startswith(name.lower() + ".exe"))
    except Exception:                               # noqa: BLE001
        return -1


def proc_count() -> int:
    """acad.exe 进程数（公开别名，供判据/用例护栏用）。"""
    return _proc_count()


def sv_dump_count(temp_dir: Optional[str] = None) -> int:
    """`%TEMP%` 里 `.sv$`（自动保存副本）的数量。

    强杀 acad.exe 后会留下它们，下次启动 AutoCAD 扫到就弹"图形修复"，
    点"关闭"也不会清 —— 这是本机长期被困扰的那个弹窗的根因。
    """
    d = temp_dir or os.environ.get("TEMP") or os.environ.get("TMP") or ""
    if not d:
        return -1
    try:
        return len(glob.glob(os.path.join(d, "*.sv$")))
    except Exception:                               # noqa: BLE001
        return -1


def snapshot(app: Any = None, temp_dir: Optional[str] = None) -> Dict[str, Any]:
    """采一份环境快照。`app` 为 None 表示 AutoCAD 未运行。"""
    from . import com

    snap: Dict[str, Any] = {
        "taken_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "running": app is not None,
        "process_count": _proc_count(),
        "sv_count": sv_dump_count(temp_dir),
        "documents": 0,
        "version": None,
        "variables": {},
    }
    if app is None:
        return snap
    snap["documents"] = com.active_documents(app)
    try:
        snap["version"] = str(app.Version)
    except Exception:                               # noqa: BLE001
        pass
    snap["variables"] = {k: com.get_var(app, k) for k in TRACKED_VARS}
    return snap


def profile_ok(snap: Dict[str, Any]) -> Optional[bool]:
    """profile 是否合规。None = 读不到（没有打开文档 / 未运行）。"""
    if not snap.get("running"):
        return None
    prof = (snap.get("variables") or {}).get("CPROFILE")
    if prof is None:
        return None
    return prof.strip() == REQUIRED_PROFILE


def diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """比较两份快照，返回漂移项（空 = 干净）。"""
    drift: Dict[str, Any] = {}
    if before.get("process_count") != after.get("process_count"):
        drift["process_count"] = [before.get("process_count"),
                                  after.get("process_count")]
    if before.get("sv_count") != after.get("sv_count"):
        drift["sv_count"] = [before.get("sv_count"), after.get("sv_count")]
    bv = before.get("variables") or {}
    av = after.get("variables") or {}
    for k in TRACKED_VARS:
        if k in bv or k in av:
            if bv.get(k) != av.get(k):
                drift["var:" + k] = [bv.get(k), av.get(k)]
    return drift


# ── 基线文件 ────────────────────────────────────────────────────────
def baseline_path() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, ".acadkit", "env_baseline.json")


def write_baseline(snap: Dict[str, Any]) -> str:
    p = baseline_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=2)
    return p


def read_baseline() -> Optional[Dict[str, Any]]:
    p = baseline_path()
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                               # noqa: BLE001
        return None
