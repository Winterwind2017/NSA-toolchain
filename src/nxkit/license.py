"""许可证清单：读本机 SPLM 的 .dat，回答"这台机器到底买了哪些 feature"。

只做**只读解析**，不启动 NX、不检入检出。用途有两个：

1. `nxkit licenses` 打印本机 feature 集与各能力族的许可归属；
2. `nxkit status` / `selftest` 在动手前提示"这条能力需要 X 许可，本机没有"。
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

DEFAULT_DAT = r"C:\ProgramData\Siemens\siemens_SSQ.dat"
INCREMENT_RE = re.compile(r"^INCREMENT\s+(\S+)")


def dat_path() -> str:
    """先看 SPLM_LICENSE_SERVER（可能是 28000@host，也可能直接是 .dat 路径）。"""
    env = os.environ.get("SPLM_LICENSE_SERVER") or os.environ.get("UGS_LICENSE_SERVER")
    if env and env.lower().endswith(".dat") and os.path.isfile(env):
        return env
    return DEFAULT_DAT


@lru_cache(maxsize=4)
def features(path: str | None = None) -> frozenset[str]:
    """返回 .dat 里所有 INCREMENT 的 feature 名（小写）。读不到就返回空集。"""
    p = path or dat_path()
    if not os.path.isfile(p):
        return frozenset()
    names: set[str] = set()
    with open(p, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            m = INCREMENT_RE.match(line)
            if m:
                names.add(m.group(1).strip().lower())
    return frozenset(names)


def has(feature: str, path: str | None = None) -> bool:
    return feature.lower() in features(path)


def missing(caps_licenses) -> list[tuple[str, str]]:
    """caps_licenses: 可迭代的 (cap_id, license)。返回本机缺许可的 (cap_id, license)。"""
    have = features()
    if not have:              # 读不到 .dat 就别误报
        return []
    return [(cid, lic) for cid, lic in caps_licenses if lic and lic.lower() not in have]


def summary(path: str | None = None) -> dict:
    feats = features(path)
    return {"dat": path or dat_path(), "count": len(feats),
            "readable": bool(feats)}
