"""快照与恢复（对照 CADCraft `crates/engine/autosave.rs` 的语义）。

我们的场景：一条能力跑失败，不该把已有图弄坏；批量跑之前应该能一键回退。
做法很土但有效：**把文件复制进快照目录 + 记 sha256**，恢复时按清单逐字节还原。

刻意不做"隐藏的自动保存"（那会让人不知道磁盘上多了什么）：
每次快照都在显式目录里，清单是普通 JSON，可读可审。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class SnapshotError(RuntimeError):
    pass


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def save_snapshot(root: str, files: List[str], *, note: str = "") -> Dict[str, object]:
    """把 files 复制到 root 下的时间戳目录，写 manifest.json。"""
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise SnapshotError("没有可快照的文件")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(root, "snap_" + stamp)
    os.makedirs(dest, exist_ok=True)
    entries: List[Dict[str, object]] = []
    for src in files:
        name = os.path.basename(src)
        target = os.path.join(dest, name)
        shutil.copy2(src, target)
        entries.append({"name": name, "source": os.path.abspath(src),
                        "bytes": os.path.getsize(target),
                        "sha256": sha256_file(target)})
    manifest = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "note": note, "dir": dest, "files": entries}
    mpath = os.path.join(dest, "manifest.json")
    with open(mpath, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    manifest["manifest"] = mpath
    return manifest


def load_manifest(manifest_path: str) -> Dict[str, object]:
    with open(manifest_path, encoding="utf-8") as fh:
        return json.load(fh)


def verify_snapshot(manifest_path: str) -> Dict[str, object]:
    """核对快照副本是否完好（防止快照自己坏了还拿它恢复）。"""
    m = load_manifest(manifest_path)
    base = os.path.dirname(manifest_path)
    bad: List[str] = []
    for entry in m.get("files") or []:
        target = os.path.join(base, str(entry["name"]))
        if not os.path.isfile(target):
            bad.append("%s：副本缺失" % entry["name"])
            continue
        if sha256_file(target) != entry["sha256"]:
            bad.append("%s：sha256 不匹配" % entry["name"])
    return {"ok": not bad, "problems": bad, "count": len(m.get("files") or [])}


def restore(manifest_path: str) -> Dict[str, object]:
    """按清单还原到**原始路径**（会覆盖当前文件，调用方要自己确认）。"""
    check = verify_snapshot(manifest_path)
    if not check["ok"]:
        raise SnapshotError("快照本身损坏：%s" % "; ".join(check["problems"]))  # type: ignore[arg-type]
    m = load_manifest(manifest_path)
    base = os.path.dirname(manifest_path)
    restored: List[str] = []
    for entry in m.get("files") or []:
        src = os.path.join(base, str(entry["name"]))
        dst = str(entry["source"])
        d = os.path.dirname(dst)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        shutil.copy2(src, dst)
        if sha256_file(dst) != entry["sha256"]:
            raise SnapshotError("还原后校验失败：%s" % dst)
        restored.append(dst)
    return {"restored": restored, "count": len(restored)}
