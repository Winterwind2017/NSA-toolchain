"""载入 `docs/registry.yaml`。

刻意**不强制依赖 PyYAML**：内核要能在没装第三方库的环境里跑
（`autocad-mcp` 的 venv 里就没有 PyYAML）。有 PyYAML 就用它，
没有就用针对本仓库格式的容错解析器（只认 `capabilities` 下的扁平结构）。
"""

from __future__ import annotations

import io
import os
from typing import Any, Dict, List, Optional

VALID_STATUS = ("verified", "usable_unjudged", "pending", "dead", "external")


def registry_path() -> str:
    """按优先级找 registry：环境变量 → 仓库内 docs/。"""
    env = os.environ.get("ACADKIT_REGISTRY")
    if env and os.path.isfile(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    # src/acadkit/registry.py → 仓库根
    root = os.path.dirname(os.path.dirname(here))
    return os.path.join(root, "docs", "registry.yaml")


def _fallback_parse(text: str) -> Dict[str, Any]:
    """只解析本仓库 registry 的子集。

    支持的形态：
        schema: 1
        target: "..."
        capabilities:
          - id: geom.line
            family: geom
            backend: [com, lisp]
            status: verified
            judge: "..."
    """
    out: Dict[str, Any] = {"capabilities": []}
    caps: List[Dict[str, Any]] = out["capabilities"]
    cur: Optional[Dict[str, Any]] = None
    in_caps = False

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("capabilities:"):
            in_caps = True
            continue
        if not in_caps:
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                out.setdefault(k.strip(), v.strip().strip('"'))
            continue
        stripped = line.strip()
        if stripped.startswith("- id:"):
            cur = {"id": stripped.split(":", 1)[1].strip()}
            caps.append(cur)
            continue
        if cur is None or ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            cur[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        else:
            cur[k] = v.strip('"')
    return out


def load(path: Optional[str] = None) -> Dict[str, Any]:
    p = path or registry_path()
    with io.open(p, encoding="utf-8") as fh:
        text = fh.read()
    try:
        import yaml
        data = yaml.safe_load(text)
    except Exception:                               # noqa: BLE001
        data = _fallback_parse(text)
    caps = data.get("capabilities") or []
    for c in caps:
        c.setdefault("backend", [])
        c.setdefault("status", "pending")
    data["capabilities"] = caps
    return data


def counts(data: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    data = data or load()
    out = {s: 0 for s in VALID_STATUS}
    for c in data["capabilities"]:
        st = c.get("status")
        if st in out:
            out[st] += 1
    out["total"] = len(data["capabilities"])
    return out


def by_status(status: str) -> List[Dict[str, Any]]:
    return [c for c in load()["capabilities"] if c.get("status") == status]


def validate(data: Optional[Dict[str, Any]] = None) -> List[str]:
    """自检：id 唯一、字段齐全、status 合法、dead 必须有替代说明。"""
    data = data or load()
    problems: List[str] = []
    seen = set()
    need = ("id", "family", "backend", "status", "source", "judge", "evidence")
    for i, c in enumerate(data["capabilities"], 1):
        cid = c.get("id")
        if not cid:
            problems.append("第 %d 条缺 id" % i)
            continue
        if cid in seen:
            problems.append("重复 id: %s" % cid)
        seen.add(cid)
        for k in need:
            if k not in c:
                problems.append("%s 缺字段 %s" % (cid, k))
        if c.get("status") not in VALID_STATUS:
            problems.append("%s 的 status 非法: %r" % (cid, c.get("status")))
        if c.get("status") == "dead" and "替代" not in str(c.get("judge", "")):
            problems.append("%s 是 dead 但没写替代方案" % cid)
        if c.get("status") == "external" and not str(c.get("judge", "")).strip():
            problems.append("%s 是 external 但没写原因" % cid)
    return problems
