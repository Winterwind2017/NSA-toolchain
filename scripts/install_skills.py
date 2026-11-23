#!/usr/bin/env python3
"""把 skills/ 装到 agent 的 skills 根，并支持增量更新。

    python scripts/install_skills.py --list
    python scripts/install_skills.py --target "$env:USERPROFILE\\.dsh\\skills"
    python scripts/install_skills.py --dry-run
    python scripts/install_skills.py --update          # 只覆盖 SKILL.md / capabilities.json

设计要点：
* 装完写 `.nsa-install.json` 清单（每个技能的 SKILL.md sha256），
  `--update` **只动清单里登记过的技能**，且只覆盖那两个文件——
  不会把你在目标目录里的本地改动冲掉；
* 默认 `--dry-run` 关，但会打印每个技能的文件数；
* 跳过 `__pycache__` / `.git` / `.pyc`。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
MANIFEST = ".nsa-install.json"
UPDATABLE = ("SKILL.md", "capabilities.json")
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules"}
SKIP_SUFFIX = {".pyc", ".pyo"}


@dataclass
class Plan:
    install: List[str] = field(default_factory=list)
    update: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    files: int = 0


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def discover(skills_root: str = SKILLS) -> Dict[str, str]:
    """{技能名: 目录}；只认含 SKILL.md 的目录。"""
    out: Dict[str, str] = {}
    if not os.path.isdir(skills_root):
        return out
    for name in sorted(os.listdir(skills_root)):
        path = os.path.join(skills_root, name)
        if os.path.isfile(os.path.join(path, "SKILL.md")):
            out[name] = path
    return out


def _walk_files(src: str) -> List[str]:
    out: List[str] = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1] in SKIP_SUFFIX:
                continue
            out.append(os.path.relpath(os.path.join(dirpath, fn), src))
    return sorted(out)


def load_manifest(target: str) -> Dict[str, object]:
    path = os.path.join(target, MANIFEST)
    if not os.path.isfile(path):
        return {"skills": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError:
        return {"skills": {}}


def make_plan(target: str, skills: Dict[str, str], *, update: bool) -> Plan:
    plan = Plan()
    manifest = load_manifest(target)
    installed = set((manifest.get("skills") or {}).keys())
    for name, src in skills.items():
        if update:
            if name in installed:
                plan.update.append(name)
            else:
                plan.skipped.append(name)
        else:
            plan.install.append(name)
        plan.files += len(_walk_files(src))
    return plan


def install(target: str, skills: Dict[str, str], *, update: bool = False,
            dry_run: bool = False) -> Dict[str, object]:
    plan = make_plan(target, skills, update=update)
    manifest = load_manifest(target)
    entries: Dict[str, object] = dict(manifest.get("skills") or {})
    done: List[Dict[str, object]] = []

    for name in plan.install + plan.update:
        src = skills[name]
        dst = os.path.join(target, name)
        if dry_run:
            done.append({"skill": name, "mode": "update" if update else "install",
                         "files": len(_walk_files(src)), "dry_run": True})
            continue
        os.makedirs(dst, exist_ok=True)
        if update:
            copied = []
            for fn in UPDATABLE:
                s = os.path.join(src, fn)
                if os.path.isfile(s):
                    shutil.copy2(s, os.path.join(dst, fn))
                    copied.append(fn)
        else:
            copied = []
            for rel in _walk_files(src):
                s = os.path.join(src, rel)
                t = os.path.join(dst, rel)
                os.makedirs(os.path.dirname(t) or dst, exist_ok=True)
                shutil.copy2(s, t)
                copied.append(rel)
        skill_md = os.path.join(dst, "SKILL.md")
        entries[name] = {"sha256": _sha256(skill_md) if os.path.isfile(skill_md) else "",
                         "files": len(copied),
                         "mode": "update" if update else "install",
                         "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        done.append({"skill": name, "mode": entries[name]["mode"],
                     "files": len(copied), "dry_run": False})

    if not dry_run:
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, MANIFEST), "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "source": SKILLS, "skills": entries},
                      fh, ensure_ascii=False, indent=2)
    return {"target": target, "dry_run": dry_run,
            "done": done, "skipped": plan.skipped,
            "total_files": plan.files}


def status(target: str, skills: Dict[str, str]) -> Dict[str, object]:
    """对比"仓库里的技能"与"已装到 target 的技能"，给出 fresh/stale/missing。

    stale = 已装但 SKILL.md 的 sha256 与仓库不同（仓库更新了、目标没跟）。
    missing = 清单里没有，或目标目录不存在。
    """
    manifest = load_manifest(target)
    entries: Dict[str, object] = dict(manifest.get("skills") or {})
    rows: List[Dict[str, object]] = []
    counts = {"fresh": 0, "stale": 0, "modified": 0, "missing": 0, "extra": 0}
    for name in sorted(skills):
        repo_sha = _sha256(os.path.join(skills[name], "SKILL.md"))
        dst = os.path.join(target, name)
        entry = entries.get(name) or {}
        inst_sha = str(entry.get("sha256") or "")
        actual_sha = _sha256(os.path.join(dst, "SKILL.md")) if os.path.isfile(
            os.path.join(dst, "SKILL.md")) else ""
        if not os.path.isdir(dst):
            state = "missing"           # 目标里没有这个技能
        elif not inst_sha:
            state = "stale"             # 目录在但清单没记哈希：无法证明同步
        elif actual_sha != inst_sha:
            state = "modified"          # 目标文件被本地改过 / 损坏
        elif inst_sha != repo_sha:
            state = "stale"             # 仓库更新了，目标没跟
        else:
            state = "fresh"
        counts[state] += 1
        rows.append({"skill": name, "state": state, "installed_sha256": inst_sha,
                     "repo_sha256": repo_sha, "installed_at": entry.get("at") or "",
                     "mode": entry.get("mode") or ""})
    extras = sorted(set(entries) - set(skills))
    counts["extra"] = len(extras)
    return {"target": target, "has_manifest": bool(entries), "rows": rows,
            "extra_in_target": extras, "counts": counts,
            "fresh": counts["fresh"] == len(skills) and not extras}


def default_target() -> str:
    home = os.path.expanduser("~")
    for cand in (os.path.join(home, ".dsh", "skills"),
                 os.path.join(home, ".claude", "skills")):
        if os.path.isdir(os.path.dirname(cand)):
            return cand
    return os.path.join(home, ".dsh", "skills")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="安装/更新 nsa-toolchain 技能")
    ap.add_argument("--target", default=default_target())
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--status", action="store_true", help="只报告已装状态（fresh/stale/missing）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    skills = discover()
    if not skills:
        print("没找到任何技能（skills/*/SKILL.md）")
        return 2

    if args.list:
        for name, path in skills.items():
            n = len(_walk_files(path))
            print("%-28s %3d 个文件  %s" % (name, n, path))
        return 0

    if args.status:
        st = status(args.target, skills)
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
            return 0 if st["fresh"] else 1
        print("目标：%s" % st["target"])
        if not st["has_manifest"]:
            print("（目标里没有 %s 清单，无法判断是否已装）" % MANIFEST)
        for row in st["rows"]:
            mark = {"fresh": "OK  ", "stale": "旧版", "modified": "被改",
                    "missing": "未装"}[row["state"]]
            extra = ""
            if row["state"] == "stale" and row["installed_at"]:
                extra = "  （装的版本：%s）" % row["installed_at"]
            print("  [%s] %-28s %s" % (mark, row["skill"], extra))
        if st["extra_in_target"]:
            print("  目标里还有仓库没有的技能：%s" % ", ".join(st["extra_in_target"]))
        c = st["counts"]
        print("结论：%s（fresh=%d stale=%d modified=%d missing=%d extra=%d）"
              % ("全部最新" if st["fresh"] else "需要 --update 或重新安装",
                 c["fresh"], c["stale"], c["modified"], c["missing"], c["extra"]))
        return 0 if st["fresh"] else 1

    out = install(args.target, skills, update=args.update, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    tag = "（演练，未写盘）" if args.dry_run else ""
    print("目标：%s%s" % (args.target, tag))
    for item in out["done"]:
        print("  %-28s %s，%d 个文件" % (item["skill"], item["mode"], item["files"]))
    for name in out["skipped"]:
        print("  %-28s 跳过（目标里没装过，--update 不新增）" % name)
    print("合计 %d 个文件" % out["total_files"])
    if not args.dry_run:
        print("清单：%s" % os.path.join(args.target, MANIFEST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
