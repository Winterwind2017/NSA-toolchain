#!/usr/bin/env python3
"""存盘无损性（真机）：DWG 存→重开→再导出 DXF，用差异比对证明"什么都没丢"。

    python tests/live_write_safety.py

规格来源：CADCraft `docs/gaps.md` 的头号 blocker——"存 DWG 会丢掉没建模的内容"。
我们的等价判据（比"实体数一致"强得多）：

1. 画一组常见实体（线/圆/弧/多段线/单行文字/多行文字）；
2. 导出 DXF 作为**基线**；
3. 存 DWG → 关文档 → 重开 DWG → 再导出 DXF；
4. `dxf.compare` 比对两次 DXF：**要求零增、零删、零改**；
5. 顺带跑 `dxf.audit`：重开后的图不应有新问题。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit.build.helpers import dbl, pt                     # noqa: E402
from acadkit.core import com, launch, plot                    # noqa: E402
from acadkit.dxf.audit import audit, report_text              # noqa: E402
from acadkit.dxf.compare import compare                       # noqa: E402
from acadkit.dxf.document import read                         # noqa: E402
from acadkit.judges.case import CaseRunner                    # noqa: E402

_WATCH = {"deadline": 0.0}


def watchdog(seconds: float) -> None:
    def loop() -> None:
        while True:
            time.sleep(1.0)
            if _WATCH["deadline"] and time.time() > _WATCH["deadline"]:
                print("!! 超时，强杀 acad")
                subprocess.run(["taskkill", "/F", "/IM", "acad.exe"], capture_output=True)
                os._exit(9)

    threading.Thread(target=loop, daemon=True).start()


def draw_fixture(doc: Any) -> int:
    """画 6 类常见实体，返回实体数。"""
    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    com.retry(lambda: ms.AddLine(pt(0, 0, 0), pt(100, 0, 0)), label="AddLine")
    com.retry(lambda: ms.AddCircle(pt(50, 50, 0), 20.0), label="AddCircle")
    com.retry(lambda: ms.AddArc(pt(0, 100, 0), 25.0, 0.0, 1.5707963), label="AddArc")
    pl = com.retry(lambda: ms.AddLightWeightPolyline(
        dbl([0, 0, 40, 0, 40, 30, 0, 30])), label="AddLightWeightPolyline")
    pl.Closed = True
    com.retry(lambda: ms.AddText("ACADKIT", pt(0, -20, 0), 3.5), label="AddText")
    com.retry(lambda: ms.AddMText(pt(0, -40, 0), 80.0, "第一行\\P第二行"),
              label="AddMText")
    return int(com.retry(lambda: ms.Count, label="Count"))


def run(workdir: str, keep: bool) -> int:
    os.makedirs(workdir, exist_ok=True)
    watchdog(180.0)
    _WATCH["deadline"] = time.time() + 170.0

    info = launch.launch()
    app = info["app"]
    print("AutoCAD：%s" % ("本次启动" if info["launched"] else "附加到已运行实例"))
    runner = CaseRunner(app, workdir, log=lambda m: print(m))
    runner.ensure_baseline_doc()

    doc = runner.new_doc("write_safety")
    n = draw_fixture(doc)
    print("已画实体数：%d" % n)

    base_dxf = os.path.join(workdir, "baseline.dxf")
    info_dxf = plot.save_as(doc, base_dxf, fmt=65)
    dwg = os.path.join(workdir, "roundtrip.dwg")
    info_dwg = plot.save_as(doc, dwg)
    checks: Dict[str, Any] = {}

    checks["dxf_exported"] = bool(info_dxf.get("ok") and os.path.getsize(base_dxf) > 500)
    checks["dwg_exported"] = bool(info_dwg.get("ok") and os.path.getsize(dwg) > 2000)

    # 关掉当前文档，重开 DWG，再导出 DXF
    try:
        runner._close(doc, "write_safety")
    except Exception as exc:                          # noqa: BLE001
        print("关文档失败：%s" % exc)
    reopened = None
    try:
        reopened = com.retry(lambda: app.Documents.Open(dwg), label="Documents.Open")
        time.sleep(0.6)
        n2 = int(com.retry(lambda: reopened.ModelSpace.Count, label="Count"))
        after_dxf = os.path.join(workdir, "after_reopen.dxf")
        info2 = plot.save_as(reopened, after_dxf, fmt=65)
        checks["reopened"] = True
        checks["entity_count_same"] = (n2 == n)
        checks["after_dxf"] = bool(info2.get("ok"))
    except Exception as exc:                          # noqa: BLE001
        print("重开失败：%s" % exc)
        after_dxf = ""
        checks.update({"reopened": False, "entity_count_same": False, "after_dxf": False})

    diff = None
    if after_dxf and os.path.isfile(after_dxf) and checks.get("after_dxf"):
        a, b = read(base_dxf), read(after_dxf)
        rep = compare(a, b)
        diff = rep.to_dict()
        checks["no_entities_lost"] = len(rep.removed) == 0
        checks["no_entities_added"] = len(rep.added) == 0
        checks["no_entities_changed"] = len(rep.changed) == 0
        print("\n=== 差异比对（基线 vs 重开后）===")
        print(rep.to_text())

        _report = audit(b)
        checks["audit_clean_after_reopen"] = bool(_report["ok"])
        print("\n=== 重开后的自检 ===")
        print(report_text(_report))

    print("\n=== 判据 ===")
    for k, v in checks.items():
        print("  %-26s %s" % (k, "PASS" if v else "FAIL"))
    passed = sum(1 for v in checks.values() if v)
    print("  合计 %d/%d" % (passed, len(checks)))

    payload = {"suite": "write_safety", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "entities": n, "files": {"baseline_dxf": base_dxf, "dwg": dwg,
                                        "after_dxf": after_dxf},
               "checks": checks, "diff": diff, "passed": passed, "total": len(checks)}
    outp = os.path.join(workdir, "results.json")
    with open(outp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    print("证据：%s" % outp)

    try:
        if reopened is not None:
            reopened.Saved = True
            reopened.Close(False)
    except Exception:                                 # noqa: BLE001
        pass
    try:
        runner._close(runner.baseline_doc, "baseline")
        if info["launched"] and not keep:
            from acadkit.judges.case import finish
            print("收尾：%s" % finish(app, None, quit_app=True))
    except Exception as exc:                          # noqa: BLE001
        print("收尾失败：%s" % exc)
    return 0 if passed == len(checks) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DWG 存盘无损性（真机）")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workdir", default=None)
    args = ap.parse_args(argv)
    wd = args.workdir or os.path.join(ROOT, "_scratch",
                                      "writesafe_%s" % time.strftime("%Y%m%d_%H%M%S"))
    return run(wd, args.keep)


if __name__ == "__main__":
    sys.exit(main())
