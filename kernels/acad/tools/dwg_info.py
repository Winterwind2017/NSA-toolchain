#!/usr/bin/env python3
"""看 DWG 的结构（不开 AutoCAD）：`python tools/dwg_info.py 图.dwg [--json]`

只报版本、维护版本、段表与自洽性——**不解析实体**（那需要位流解码，另立项目）。
退出码 = 问题数。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit.dwg.header import DwgError, read_header, summary_text   # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DWG 结构读取（版本/段表）")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        header = read_header(args.path)
    except DwgError as exc:
        print("读不了：%s" % exc)
        return 2
    if args.json:
        print(json.dumps(header.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(summary_text(header))
    return len(header.problems)


if __name__ == "__main__":
    sys.exit(main())
