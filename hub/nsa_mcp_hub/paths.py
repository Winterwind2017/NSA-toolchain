"""路径解析：所有默认路径都从本文件的位置推导，仓库克隆到任意目录都能用。

外部程序与外部仓库用环境变量覆盖（都不设也能跑离线部分）：

    NSA_PYTHON        指定 Python 解释器（默认当前解释器）
    NSA_ACAD_EXE      AutoCAD 可执行文件
    NSA_SW_EXE        SolidWorks 可执行文件
    NSA_NX_EXE        NX 可执行文件（run_journal）
    NSA_CCX           CalculiX ccx 求解器
    NSA_CAD_VIEWER    cad-viewer 技能目录
    NSA_MCP_HUB_RUNS  运行时产物目录（默认 hub/_runs）
    CAD_AGENT_HUB     CAD-Agent-Hub 根目录（CATIA / EPLAN 代理需要）
    <KIT>KIT_SRC      内核源码目录：ACADKIT_SRC / SWKIT_SRC / NXKIT_SRC /
                      GXKIT_SRC / CODESYSKIT_SRC / AUTOSHOPKIT_SRC

约定：本模块只做"解析"，不创建目录、不校验进程、不 import 任何内核。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# hub/nsa_mcp_hub/paths.py -> 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]
HUB_DIR = REPO_ROOT / "hub"
KERNELS_DIR = REPO_ROOT / "kernels"
SKILLS_DIR = REPO_ROOT / "skills"


def repo_path(*parts: str) -> Path:
    """仓库内路径，例如 repo_path("kernels", "acad", "src")。"""
    return REPO_ROOT.joinpath(*parts)


def src_dir(kit: str, env_name: str | None = None) -> str:
    """内核源码目录：环境变量优先，否则 <repo>/kernels/<kit>/src。"""
    name = env_name or "%sKIT_SRC" % kit.upper()
    value = os.environ.get(name)
    if value:
        return value
    return str(KERNELS_DIR / kit / "src")


def kernel_dir(kit: str, env_name: str | None = None) -> str:
    """内核目录（不含 /src）：环境变量优先，否则 <repo>/kernels/<kit>。"""
    return str(Path(src_dir(kit, env_name)).parent)


def runs_dir() -> str:
    """验收/运行为产物目录，默认 hub/_runs（gitignore 里已排除）。"""
    return os.environ.get("NSA_MCP_HUB_RUNS") or str(HUB_DIR / "_runs")


def python_exe() -> str:
    """要用的 Python 解释器：NSA_PYTHON 优先，默认当前解释器。"""
    return os.environ.get("NSA_PYTHON") or sys.executable


def find_exe(env_name: str, *candidates: str) -> str:
    """按「环境变量 → 给定候选路径 → PATH」找可执行文件，找不到返回空串。"""
    value = os.environ.get(env_name)
    if value:
        path = Path(os.path.expandvars(os.path.expanduser(value)))
        if path.exists():
            return str(path)
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(os.path.expandvars(os.path.expanduser(candidate)))
        if path.exists():
            return str(path)
        found = shutil.which(candidate)
        if found:
            return found
    return ""


# 常见安装位置只作为「找不到时再试」的兜底，不参与任何判断
ACAD_EXE = find_exe(
    "NSA_ACAD_EXE",
    r"C:\Program Files\Autodesk\AutoCAD 2025\acad.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2024\acad.exe",
    "acad.exe",
)
SW_EXE = find_exe(
    "NSA_SW_EXE",
    r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe",
    "SLDWORKS.exe",
)
NX_EXE = find_exe("NSA_NX_EXE", "run_journal.exe", "ugraf.exe")
CCX_EXE = find_exe(
    "NSA_CCX",
    "ccx_i4_static.exe",
    "ccx_i8_static.exe",
    "ccx",
)
CAD_VIEWER_DIR = os.environ.get("NSA_CAD_VIEWER") or ""
CAD_AGENT_HUB = os.environ.get("CAD_AGENT_HUB") or ""
