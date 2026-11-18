#!/usr/bin/env python3
"""审一份 DXF：`python tools/audit_dxf.py 图.dxf [--json]`

不需要 AutoCAD，也不需要 Windows——纯文件结构检查。
退出码 = error 级问题数（可以直接放进 CI 当门）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit.dxf.audit import audit, report_text           # noqa: E402
from acadkit.dxf.document import DxfError, read           # noqa: E402
from acadkit.dxf.io import sniff                          # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DXF 图纸自检（离线）")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--encoding", default=None)
    args = ap.parse_args(argv)

    try:
        kind = sniff(args.path)
        if kind["format"] not in ("dxf", "dxf-binary"):
            print("不是 DXF（探测到 %s）；本工具只审 DXF" % kind["format"])
            return 2
        doc = read(args.path, encoding=args.encoding)
        result = audit(doc)
    except DxfError as exc:
        print("读不了：%s" % exc)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(report_text(result))
    return int(result["counts"].get("error", 0))


if __name__ == "__main__":
    sys.exit(main())
