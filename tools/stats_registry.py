"""统计 registry.yaml 的分布，生成 P0 总结里的数字（避免手写漂移）。"""

from __future__ import annotations

import io
import re
from collections import Counter

P = r"D:\bililive\acadkit\docs\registry.yaml"
text = io.open(P, encoding="utf-8").read()

# 极简解析：按 "- id:" 切块
blocks = re.split(r"\n  - id: ", text)[1:]
rows = []
for b in blocks:
    cid = b.split("\n")[0].strip()
    fam = re.search(r"\n    family: (\S+)", b)
    status = re.search(r"\n    status: (\S+)", b)
    backend = re.search(r"\n    backend: \[([^\]]*)\]", b)
    rows.append({
        "id": cid,
        "family": fam.group(1) if fam else "?",
        "status": status.group(1) if status else "?",
        "backend": [x.strip() for x in backend.group(1).split(",") if x.strip()] if backend else [],
    })

print("条目总数:", len(rows))
print()
print("=== 状态分布 ===")
for k, v in Counter(r["status"] for r in rows).most_common():
    print("  %-16s %d" % (k, v))
print()
print("=== 能力族分布 ===")
for k, v in Counter(r["family"] for r in rows).most_common():
    print("  %-14s %d" % (k, v))
print()
print("=== 后端覆盖（可多选）===")
for k, v in Counter(b for r in rows for b in r["backend"]).most_common():
    print("  %-10s %d" % (k, v))
print()
none_be = [r["id"] for r in rows if not r["backend"]]
print("无后端（dead/待补）:", len(none_be))
print("  " + ", ".join(none_be))
