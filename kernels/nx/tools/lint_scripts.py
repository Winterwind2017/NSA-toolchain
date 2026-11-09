"""先编译再执行：给一次性脚本（`_*.py`）和 tools/ 做语法体检。

背景：这个仓库里反复出现同一类事故——写一次性生成/探针脚本时，在**中文字符串里用了
ASCII 双引号**，于是脚本自己 SyntaxError，而它本该生成/更新的文档根本没被写出去，
错误往往到几十分钟后才被发现（2026-10-22 一天内犯了 5 次）。

用法：
    python tools/lint_scripts.py                 # 默认：仓库根 _*.py + tools/*.py
    python tools/lint_scripts.py a.py b.py       # 指定文件
    python tools/lint_scripts.py --all           # 再加 tests/ 与 src/ 下的全部 .py
    python tools/lint_scripts.py --quiet         # 只报失败

退出码：0 全过；1 有编译失败。
"""

from __future__ import annotations

import argparse
import pathlib
import py_compile
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CJK = range(0x4E00, 0xA000)
# ASCII 引号夹在两个汉字之间，是「中文里用了英文引号」最典型的形态
STRAY_QUOTE = re.compile(r"[\u4e00-\u9fff]\"[\u4e00-\u9fff]")


def _has_cjk(s: str) -> bool:
    return any(ord(ch) in CJK for ch in s)


def _quote_hint(line: str) -> str | None:
    """中文串里混进 ASCII 引号 → 提示改用「」。"""
    if not _has_cjk(line):
        return None
    if STRAY_QUOTE.search(line) or line.count('"') % 2 == 1:
        return ("这一行有中文，且 ASCII 引号夹在中文之间（或数量为奇数）："
                "大概率是把中文引号写成了 ASCII 的引号，改成「」即可。")
    return None


def lint_one(path: pathlib.Path) -> str | None:
    """返回 None 表示通过，否则返回错误描述（可能多行）。"""
    try:
        py_compile.compile(str(path), cfile=str(path) + ".pyc-tmp", doraise=True)
    except py_compile.PyCompileError as exc:
        e = exc.exc_value
        lines = [f"{path}: {type(e).__name__}: {e.msg} (line {e.lineno})"]
        text = getattr(e, "text", None)
        if text:
            lines.append("    " + text.rstrip())
            hint = _quote_hint(text)
            if hint:
                lines.append("    HINT: " + hint)
        elif getattr(e, "lineno", None):
            try:
                src = path.read_text(encoding="utf-8").splitlines()
                bad = src[e.lineno - 1]
                lines.append("    " + bad.strip())
                hint = _quote_hint(bad)
                if hint:
                    lines.append("    HINT: " + hint)
            except Exception:
                pass
        return "\n".join(lines)
    except OSError as exc:
        return f"{path}: 读不到文件（{exc}）"
    finally:
        try:
            pathlib.Path(str(path) + ".pyc-tmp").unlink()
        except OSError:
            pass
    return None


def collect(args: argparse.Namespace) -> list[pathlib.Path]:
    if args.paths:
        return [pathlib.Path(p) for p in args.paths]
    files = sorted(ROOT.glob("_*.py")) + sorted((ROOT / "tools").glob("*.py"))
    if args.all:
        files += sorted((ROOT / "tests").glob("*.py"))
        files += sorted((ROOT / "src").rglob("*.py"))
    seen = set()
    out = []
    for f in files:
        rp = f.resolve()
        if rp in seen or not rp.is_file():
            continue
        seen.add(rp)
        out.append(rp)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="对一次性脚本做 py_compile 体检")
    ap.add_argument("paths", nargs="*", help="要检查的文件（默认 _*.py + tools/*.py）")
    ap.add_argument("--all", action="store_true", help="同时检查 tests/ 与 src/")
    ap.add_argument("--quiet", action="store_true", help="只报失败")
    args = ap.parse_args(argv)

    files = collect(args)
    bad = 0
    for f in files:
        err = lint_one(f)
        if err:
            bad += 1
            print(err)
    if bad:
        print(f"失败：{bad}/{len(files)} 个文件编译不过")
        return 1
    if not args.quiet:
        print(f"OK：{len(files)} 个文件全部编译通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
