"""源码可编译性检查：任何 .py 不许有语法错。

起因：改代码时两次把中文引号塞进双引号字符串（`"…"人-小时"…"`），
生成器直接语法错。CI 里很多 tools/*.py 并不会被 import，所以单独编译一遍。
"""

from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIRS = ("src", "tools", "tests")


def _py_files():
    for d in DIRS:
        base = os.path.join(ROOT, d)
        for dirpath, _dirnames, filenames in os.walk(base):
            if "__pycache__" in dirpath:
                continue
            for name in filenames:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def test_all_sources_compile() -> None:
    bad = []
    for path in _py_files():
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        try:
            compile(src, path, "exec")          # 只编译，不写 .pyc（Windows 上 cfile=devnull 不行）
        except SyntaxError as exc:
            bad.append("%s:%s: %s" % (os.path.relpath(path, ROOT), exc.lineno, exc.msg))
    assert not bad, "有文件语法错：\n" + "\n".join(bad)


def test_no_chinese_quote_in_py_strings() -> None:
    """粗查：一行里同时出现 ASCII 双引号与中文引号，最容易造成语法错/显示错。"""
    import re

    suspicious = []
    for path in _py_files():
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                code = line.split("#", 1)[0]
                if '"' in code and re.search("[\u201c\u201d]", code):
                    suspicious.append("%s:%d" % (os.path.relpath(path, ROOT), lineno))
    assert not suspicious, "疑似中英引号混用：\n" + "\n".join(suspicious[:10])
