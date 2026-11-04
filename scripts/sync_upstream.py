#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""上游同步：把 CAD-Agent-Hub（GitHub）的新提交拉进来，并保证本地补丁还能重放。

本地约定（重要）：`D:\bililive\CAD-Agent-Hub` **不是 clone**，是"上游快照 + 我们的补丁"。
所以每次同步必须证明三件事，脚本逐个验：

  1. **基线**：上游 ref 解析成具体 commit（默认 main）；
  2. **差异**：本地各 kit 与上游相比新增/修改/删除分别有哪些文件；
  3. **补丁可重放**：把 `docs/patches/*.patch` 打到上游副本上，结果必须与本地**逐字节相同**。

用法：
    python scripts/sync_upstream.py                 # 只检查（默认，只读）
    python scripts/sync_upstream.py --verify        # 只做补丁重放等价性验证
    python scripts/sync_upstream.py --regen-patches # 重新生成 docs/patches/*.patch
    python scripts/sync_upstream.py --apply --yes   # 真同步：备份 → 换文件 → 重放补丁 → 编译

退出码：正常 0；补丁冲突/编译失败/需要 --yes 却未给 → 1。
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_URL = "https://github.com/Cai-aa/CAD-Agent-Hub"
KITS = ("UG", "Solidworks", "CATIA", "EPLAN")
# 本地重编译的产物：不参与补丁/同步（同源码不同构建元数据，二进制必然不同）
BIN_SUFFIXES = {".dll", ".exe", ".pyd", ".so", ".dylib", ".pyc", ".lib", ".exp", ".obj"}
# 运行时产物（NX/SW 存出来的零件、日志、图），既不是源码也不该进补丁
ARTIFACT_SUFFIXES = {".prt", ".prtdot", ".asm", ".log", ".dxf", ".dwg", ".png", ".bmp",
                     ".jpg", ".jpeg", ".xlsx", ".xls", ".pdf", ".stp", ".step", ".igs",
                     ".iges", ".x_t", ".x_b", ".stl", ".sat", ".jsonl"}
ARTIFACT_DIRS = {"workspace", "private", "__pycache__", "logs", "output"}
HUB = Path(__file__).resolve().parent.parent


def local_root() -> Path:
    import os
    return Path(os.environ.get("CAD_AGENT_HUB", r"D:\bililive\CAD-Agent-Hub"))


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError("%s 失败（%d）：%s" % (" ".join(cmd[:3]), proc.returncode,
                                                (proc.stderr or proc.stdout).strip()[:400]))
    return proc


def ensure_upstream(ref: str, cache: Path) -> tuple[Path, str]:
    """浅克隆到缓存目录（存在则 fetch），返回 (路径, 实际 commit)。"""
    if not (cache / ".git").exists():
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--quiet", "--depth", "1", "--branch", ref, REPO_URL, str(cache)])
    else:
        run(["git", "-C", str(cache), "fetch", "--quiet", "--depth", "1", "origin", ref])
        run(["git", "-C", str(cache), "checkout", "--quiet", "FETCH_HEAD"])
    commit = run(["git", "-C", str(cache), "rev-parse", "HEAD"]).stdout.strip()
    return cache, commit


def sha(path: Path) -> str:
    """内容哈希；文本文件先规范化换行。

    上游是 git checkout（Windows 上 core.autocrlf 给 CRLF），本地是快照（LF）。
    只比原始字节会把「只差换行」的文件全判成不同（实测 UG 61/61 全中）。
    """
    data = path.read_bytes()
    if b"\x00" not in data:                      # 非二进制才规范化
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def kit_files(base: Path, kit: str) -> dict[str, Path]:
    root = base / "MCP" / kit
    if not root.is_dir():
        return {}
    return {str(p.relative_to(root)).replace("\\", "/"): p
            for p in root.rglob("*")
            if p.is_file()
            and not (ARTIFACT_DIRS & set(p.parts))
            and p.suffix.lower() not in BIN_SUFFIXES
            and p.suffix.lower() not in ARTIFACT_SUFFIXES}


def diff_kit(up: Path, loc: Path, kit: str) -> dict:
    a = kit_files(up, kit)
    b = kit_files(loc, kit)
    added = sorted(set(b) - set(a))       # 本地有、上游没有
    removed = sorted(set(a) - set(b))     # 上游有、本地没有
    modified = sorted(k for k in set(a) & set(b) if sha(a[k]) != sha(b[k]))
    return {"kit": kit, "added": added, "removed": removed, "modified": modified,
            "upstream_files": len(a), "local_files": len(b)}


def binary_drift(up: Path, loc: Path, kit: str) -> list[str]:
    """本地重编译产物与上游不同的清单（只报告，不参与补丁/同步）。"""
    a, b = up / "MCP" / kit, loc / "MCP" / kit
    if not a.is_dir():
        return []
    rows = []
    for src in a.rglob("*"):
        if not src.is_file() or src.suffix.lower() not in BIN_SUFFIXES:
            continue
        rel = src.relative_to(a)
        dst = b / rel
        if not dst.is_file():
            rows.append("%s（本地缺失）" % rel)
        elif sha(src) != sha(dst):
            rows.append(str(rel))
    return sorted(rows)


def patch_files() -> list[Path]:
    return sorted((HUB / "docs" / "patches").glob("*.patch"))


def patched_paths() -> list[str]:
    """补丁里 +++ b/... 的路径（相对 CAD-Agent-Hub 根）。"""
    paths = []
    for patch in patch_files():
        for line in patch.read_text(encoding="utf-8").splitlines():
            if line.startswith("+++ b/"):
                paths.append(line[6:].strip())
    return sorted(set(paths))


def verify_replay(up: Path, loc: Path) -> tuple[bool, list[str]]:
    """把补丁打到上游副本上，与本地逐字节比对。"""
    if not patch_files():
        return True, ["没有补丁文件，跳过重放验证"]
    notes: list[str] = []
    ok = True
    with tempfile.TemporaryDirectory(prefix="sync-verify-") as tmp:
        scratch = Path(tmp) / "tree"
        shutil.copytree(up / "MCP", scratch / "MCP")
        for patch in patch_files():
            proc = run(["git", "apply", "-p1", "--verbose", str(patch)],
                       cwd=scratch, check=False)
            notes.append("apply %s → rc=%d" % (patch.name, proc.returncode))
            if proc.returncode != 0:
                ok = False
                notes.append((proc.stderr or proc.stdout).strip()[:300])
        if ok:
            for rel in patched_paths():
                left = scratch / rel
                right = loc / rel
                if not left.is_file() or not right.is_file():
                    ok = False
                    notes.append("缺文件：%s" % rel)
                    continue
                if sha(left) != sha(right):
                    ok = False
                    notes.append("重放后与本地不一致：%s" % rel)
            if ok:
                notes.append("补丁重放结果与本地逐字节一致（%d 个文件）" % len(patched_paths()))
    return ok, notes


def regen_patches(up: Path, loc: Path) -> list[Path]:
    """按 a/MCP/... b/MCP/... 的规范形式重生成补丁（可移植、可 git apply -p1）。"""
    out_dir = HUB / "docs" / "patches"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for kit in KITS:
        diff = diff_kit(up, loc, kit)
        if not diff["modified"]:
            continue
        with tempfile.TemporaryDirectory(prefix="sync-regen-%s-" % kit) as tmp:
            stage = Path(tmp)
            (stage / "a" / "MCP" / kit).mkdir(parents=True, exist_ok=True)
            (stage / "b" / "MCP" / kit).mkdir(parents=True, exist_ok=True)
            # 只收「上游有、本地也改了」的文件：那才是我们叠加在上游上的补丁。
            # 本地新增的资产（自己的脚本/产物）由 --check 报告，同步时不动。
            if not diff["modified"]:
                continue
            for rel in diff["modified"]:
                for side, base in (("a", up), ("b", loc)):
                    src = base / "MCP" / kit / rel
                    dst = stage / side / "MCP" / kit / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            proc = run(["git", "--no-pager", "diff", "--no-index", "--no-color",
                        "--src-prefix=a/", "--dst-prefix=b/", "--", "a", "b"],
                       cwd=stage, check=False)
            text = proc.stdout or ""
            text = text.replace("a/a/", "a/").replace("b/b/", "b/")
            if not text.strip():
                continue
            target = out_dir / ("%s.patch" % kit.lower())
            target.write_text(text, encoding="utf-8", newline="\n")
            written.append(target)
    # 补丁是本脚本的生成物：这轮没写出来的旧补丁删掉，避免残留误导
    for stale in out_dir.glob("*.patch"):
        if stale not in written:
            stale.unlink()
            print("  删除过期补丁 %s" % stale.name)
    return written


def compile_tree(root: Path, files: list[str]) -> tuple[bool, list[str]]:
    notes = []
    ok = True
    for rel in files:
        if not rel.endswith(".py"):
            continue
        proc = run([sys.executable, "-m", "py_compile", str(root / rel)], check=False)
        if proc.returncode != 0:
            ok = False
            notes.append("%s：%s" % (rel, (proc.stderr or "").strip().splitlines()[-1:][0]
                                     if (proc.stderr or "").strip() else "编译失败"))
    return ok, notes


def apply_sync(up: Path, loc: Path) -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    touched: list[str] = []
    for kit in KITS:
        diff = diff_kit(up, loc, kit)
        if not (diff["added"] or diff["removed"] or diff["modified"]):
            continue
        backup = loc / ("_snapshot-MCP-%s-%s" % (kit, stamp))
        shutil.copytree(loc / "MCP" / kit, backup)
        print("  备份 %s → %s" % (kit, backup.name))
        for rel in diff["removed"]:
            target = loc / "MCP" / kit / rel
            if target.is_file():
                target.unlink()
                print("    删除本地文件 %s（上游已无）" % rel)
        for rel in set(diff["modified"]) | set(diff["added"]):
            src = up / "MCP" / kit / rel
            dst = loc / "MCP" / kit / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            touched.append(rel)
            print("    同步 %s" % rel)
    for patch in patch_files():
        proc = run(["git", "apply", "-p1", str(patch)], cwd=loc, check=False)
        print("  重放 %s → rc=%d" % (patch.name, proc.returncode))
        if proc.returncode != 0:
            print((proc.stderr or proc.stdout).strip()[:400])
            print("补丁冲突，已保留备份；请手工处理后再跑 --verify")
            return 1
    ok, notes = compile_tree(loc, touched)
    for note in notes:
        print("  编译：%s" % note)
    print("  编译通过" if ok else "  编译失败")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="CAD-Agent-Hub 上游同步 / 补丁重放验证")
    parser.add_argument("--ref", default="main", help="上游分支或 tag（默认 main）")
    parser.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "cad-hub-upstream"),
                        help="上游克隆缓存目录")
    parser.add_argument("--verify", action="store_true", help="只验证补丁重放等价性")
    parser.add_argument("--regen-patches", action="store_true", help="重生成 docs/patches/*.patch")
    parser.add_argument("--apply", action="store_true", help="真同步（会改 CAD-Agent-Hub）")
    parser.add_argument("--yes", action="store_true", help="配合 --apply，确认改本地")
    args = parser.parse_args()

    loc = local_root()
    if not (loc / "MCP").is_dir():
        print("找不到本地 CAD-Agent-Hub/MCP：%s" % loc)
        return 1

    cache = Path(args.cache)
    print("上游：%s @ %s" % (REPO_URL, args.ref))
    up, commit = ensure_upstream(args.ref, cache)
    print("解析到 commit：%s" % commit)
    print("本地：%s（快照 + 补丁，不是 clone）\n" % loc)

    if args.regen_patches:
        written = regen_patches(up, loc)
        for path in written:
            print("  重生成 %s（%d 字节）" % (path.relative_to(HUB), path.stat().st_size))
        print("\n下一步跑 --verify 确认能重放。")
        return 0

    if args.apply:
        if not args.yes:
            print("--apply 会改 %s，确认请加 --yes" % loc)
            return 1
        return apply_sync(up, loc)

    # 默认：差异概览（只读）
    total = 0
    for kit in KITS:
        diff = diff_kit(up, loc, kit)
        if not (diff["added"] or diff["removed"] or diff["modified"]):
            print("[%s] 与上游一致（%d 个文件）" % (kit, diff["upstream_files"]))
            continue
        total += len(diff["added"]) + len(diff["removed"]) + len(diff["modified"])
        print("[%s] 上游 %d / 本地 %d" % (kit, diff["upstream_files"], diff["local_files"]))
        for label, items in (("上游新增（本地没有）", diff["removed"]),
                             ("本地新增", diff["added"]),
                             ("内容不同", diff["modified"])):
            if items:
                print("  %s %d：%s" % (label, len(items),
                                       ", ".join(items[:6]) + (" …" if len(items) > 6 else "")))
    print("\n差异合计 %d 个文件（含我们自己的补丁）" % total)

    for kit in KITS:
        drift = binary_drift(up, loc, kit)
        if drift:
            print("[%s] 本地重编译的二进制 %d 个（不同步，同源码不同构建元数据）：%s"
                  % (kit, len(drift), ", ".join(drift[:4]) + (" …" if len(drift) > 4 else "")))

    ok, notes = verify_replay(up, loc)
    print("\n补丁重放验证：%s" % ("通过" if ok else "失败"))
    for note in notes:
        print("  " + note)
    if not patch_files():
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
