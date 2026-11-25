"""定位本机已经安装的焊件轮廓，不把 SolidWorks 自带库复制进仓库。"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

__all__ = ["profile_roots", "default_profile", "list_profiles"]

_PREFERRED = (
    ("iso", "square tube.sldlfp"),
    ("GB", "square-rods.sldlfp"),
    ("ansi", "tube square.sldlfp"),
)


def profile_roots() -> List[str]:
    roots: List[str] = []
    env = os.environ.get("NSA_WELDMENT_PROFILES", "").strip()
    if env:
        roots.append(env)
    program_data = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
    for vendor in ("SOLIDWORKS", "SolidWorks"):
        base = os.path.join(program_data, vendor)
        if not os.path.isdir(base):
            continue
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            candidate = os.path.join(base, name, "weldment profiles")
            if os.path.isdir(candidate):
                roots.append(candidate)
    seen = set()
    unique = []
    for root in roots:
        key = os.path.normcase(os.path.abspath(root))
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def list_profiles(root: Optional[str] = None) -> List[Dict[str, str]]:
    rows = []
    roots = [root] if root else profile_roots()
    for base in roots:
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                if not name.lower().endswith(".sldlfp"):
                    continue
                path = os.path.join(dirpath, name)
                rows.append({
                    "path": path,
                    "standard": os.path.basename(os.path.dirname(path)),
                    "name": name,
                })
    return rows


def default_profile() -> Optional[Dict[str, str]]:
    """优先 ISO 方管，其次 GB 方钢、ANSI 方管。"""
    rows = list_profiles()
    by_key = {
        (row["standard"].lower(), row["name"].lower()): row
        for row in rows
    }
    for standard, name in _PREFERRED:
        found = by_key.get((standard.lower(), name.lower()))
        if found and os.path.isfile(found["path"]):
            return found
    return rows[0] if rows else None
