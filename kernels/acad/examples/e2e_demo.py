#!/usr/bin/env python3
"""e2e_demo.py —— 一条命令演示内核：建图 → 读回 → 判据 → 导出。

    python examples/e2e_demo.py --out D:/acadkit-demo
    python examples/e2e_demo.py --only geom,dim,export --keep

跑的是**真机**（会启动 AutoCAD），每步都带判据；产物（DWG/DXF/PDF 与
results.json）写到 `--out`。想只跑离线测试用 `python tests/run_all.py --skip-live`。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import caps, live          # noqa: E402

DEFAULT = ["frame.titleblock", "table.bom", "geom.circle", "geom.rect",
           "dim.linear", "dim.diametric", "export.dwg", "export.dxf",
           "export.pdf"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="acadkit 端到端演示（真机）")
    ap.add_argument("--out", default=None, help="产物目录（默认 _scratch/demo_*）")
    ap.add_argument("--only", default=None,
                    help="要跑的能力 id，逗号分隔（默认 9 条）")
    ap.add_argument("--keep", action="store_true", help="跑完不退出 AutoCAD")
    args = ap.parse_args(argv)

    ids = [x.strip() for x in args.only.split(",")] if args.only else DEFAULT
    cases = [caps.get(i).case() for i in ids]
    out = args.out or os.path.join(ROOT, "_scratch",
                                   "demo_%s" % os.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out, exist_ok=True)

    payload = live.run(cases, workdir=out, keep=args.keep, prefix="demo")
    print(live.summarize(payload))
    print("\n产物目录：%s" % out)
    for name in sorted(os.listdir(out)):
        path = os.path.join(out, name)
        if os.path.isfile(path):
            print("  %-28s %8d B" % (name, os.path.getsize(path)))
    print("\n结论：%s" % ("全部通过" if payload.get("ok") else "有失败，见 results.json"))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
