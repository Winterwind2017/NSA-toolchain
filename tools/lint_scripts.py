"""编译体检：一次性脚本/工具脚本先过一遍语法（同 nxkit 的做法）。"""

from __future__ import annotations

import argparse
import pathlib
import py_compile
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def lint_one(path: pathlib.Path) -> str | None:
    try:
        py_compile.compile(str(path), cfile=str(path) + ".pyc-tmp", doraise=True)
        return None
    except py_compile.PyCompileError as exc:
        e = exc.exc_value
        return "%s: %s: %s (line %s)" % (path, type(e).__name__, e.msg, e.lineno)
    finally:
        try:
            pathlib.Path(str(path) + ".pyc-tmp").unlink()
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    if a.paths:
        files = [pathlib.Path(p) for p in a.paths]
    else:
        files = sorted(ROOT.glob("_*.py")) + sorted((ROOT / "tools").glob("*.py"))
        if a.all:
            files += sorted((ROOT / "tests").glob("*.py")) + sorted((ROOT / "src").rglob("*.py"))
    bad = 0
    for f in files:
        if not f.is_file():
            continue
        err = lint_one(f)
        if err:
            bad += 1
            print(err)
    if bad:
        print("失败：%d/%d 编译不过" % (bad, len(files)))
        return 1
    print("OK：%d 个文件编译通过" % len(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
