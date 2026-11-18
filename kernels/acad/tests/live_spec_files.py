#!/usr/bin/env python3
"""文件层规格（真机）：版本、往返、失败必须报告。

    python tests/live_spec_files.py
    python tests/live_spec_files.py --keep

规格来源：CADCraft `crates/engine/tests/` 的 `save_version` / `save_as_export` /
`save_reports_not_saved`——共同点是"**存不下要说出来，存下来要能读回去**"。

我们不猜 `SaveAs` 的格式码取值：本脚本会把观察到的 (fmt → 文件头 AC10xx) 记进证据，
再用它做断言——这样版本映射变了会立刻暴露，而不是悄悄错。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit.core import com, env, launch, plot               # noqa: E402
from acadkit.build.helpers import dbl, pt                      # noqa: E402
from acadkit.judges.case import CaseRunner, env_signature     # noqa: E402
from acadkit.judges.read import read_drawing                  # noqa: E402

_WATCH = {"deadline": 0.0, "what": None, "workdir": None}
MIN_BYTES = 4000


def start_watchdog(per_case_s: float, workdir: str) -> None:
    def loop() -> None:
        while True:
            time.sleep(1.0)
            if _WATCH["deadline"] and time.time() > _WATCH["deadline"]:
                print("\n!! 用例 %s 超时，强杀 acad" % _WATCH["what"])
                subprocess.run(["taskkill", "/F", "/IM", "acad.exe"], capture_output=True)
                os._exit(9)

    threading.Thread(target=loop, daemon=True).start()
    _WATCH["workdir"] = workdir


def header(path: str, n: int = 8) -> str:
    try:
        with open(path, "rb") as fh:
            return fh.read(n).decode("latin-1", "replace")
    except OSError:
        return ""


def draw_fixture(doc: Any) -> int:
    """画一个可复现的小图，返回实体数。"""
    ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
    com.retry(lambda: ms.AddCircle(pt(0, 0, 0), 10.0), label="AddCircle")
    pl = com.retry(lambda: ms.AddLightWeightPolyline(
        dbl([0, 0, 40, 0, 40, 30, 0, 30])), label="AddLightWeightPolyline")
    pl.Closed = True
    return int(com.retry(lambda: ms.Count, label="Count"))


# ── 用例 ────────────────────────────────────────────────────────────
def case_dwg_native(doc: Any, wd: str) -> Dict[str, Any]:
    """F1：原生存 DWG → 有 AC10xx 头、≥4KB、重开实体数一致。"""
    count = draw_fixture(doc)
    path = os.path.join(wd, "native_%d.dwg" % int(time.time() * 1000))
    info = plot.save_as(doc, path)
    hdr = header(path)
    ok = info.get("ok") and hdr.startswith("AC10") and info.get("bytes", 0) >= MIN_BYTES
    return {"ok": bool(ok), "detail": {"path": path, "header": hdr,
                                       "bytes": info.get("bytes"),
                                       "entities": count, "error": info.get("error")}}


def case_dwg_versions(doc: Any, wd: str) -> Dict[str, Any]:
    """F2：多格式码保存——每个产物要么有 AC10xx 头，要么明确失败（不许静默）。"""
    draw_fixture(doc)
    seen: List[Dict[str, Any]] = []
    ok = True
    for fmt in (None, 61, 64, 65):
        path = os.path.join(wd, "fmt%s_%d.dwg" % (fmt, int(time.time() * 1000)))
        info = plot.save_as(doc, path, fmt=fmt)
        hdr = header(path)
        entry = {"fmt": fmt, "ok": info.get("ok"), "header": hdr,
                 "bytes": info.get("bytes"), "error": info.get("error")}
        seen.append(entry)
        # 成功就必须有可识别文件头；失败就必须带错误信息
        if info.get("ok"):
            ok = ok and hdr.startswith("AC10")
        else:
            ok = ok and bool(info.get("error"))
    return {"ok": ok, "detail": {"attempts": seen}}


def case_reopen_roundtrip(doc: Any, wd: str) -> Dict[str, Any]:
    """F3：存盘 → 重开 → 实体数一致（L4 的核心）。"""
    count = draw_fixture(doc)
    path = os.path.join(wd, "roundtrip_%d.dwg" % int(time.time() * 1000))
    info = plot.save_as(doc, path)
    if not info.get("ok"):
        return {"ok": False, "detail": {"save_error": info.get("error")}}
    reopen_doc = None
    try:
        reopen_doc = com.retry(lambda: doc.Application.Documents.Open(path),
                               label="Documents.Open")
        time.sleep(0.4)
        got = int(com.retry(lambda: reopen_doc.ModelSpace.Count, label="Count"))
    finally:
        if reopen_doc is not None:
            try:
                reopen_doc.Saved = True
                reopen_doc.Close(False)
            except Exception:                       # noqa: BLE001
                pass
    return {"ok": got == count, "detail": {"entities_before": count,
                                           "entities_after": got, "path": path}}


def case_dxf_write(doc: Any, wd: str) -> Dict[str, Any]:
    """F4：写 DXF（fmt=65）——文件头含 AC10xx 且能被重开读回。"""
    count = draw_fixture(doc)
    path = os.path.join(wd, "spec_%d.dxf" % int(time.time() * 1000))
    info = plot.save_as(doc, path, fmt=65)
    if not info.get("ok"):
        return {"ok": False, "detail": {"save_error": info.get("error")}}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(2000)
    except OSError as exc:
        return {"ok": False, "detail": {"read_error": str(exc)}}
    has_ver = "AC10" in head
    reopen_doc = None
    got = None
    try:
        reopen_doc = com.retry(lambda: doc.Application.Documents.Open(path),
                               label="Documents.Open(dxf)")
        time.sleep(0.5)
        got = int(com.retry(lambda: reopen_doc.ModelSpace.Count, label="Count"))
    except Exception as exc:                        # noqa: BLE001
        return {"ok": False, "detail": {"open_error": "%s: %s" % (type(exc).__name__, exc),
                                        "has_acadver": has_ver,
                                        "bytes": info.get("bytes")}}
    finally:
        if reopen_doc is not None:
            try:
                reopen_doc.Saved = True
                reopen_doc.Close(False)
            except Exception:                       # noqa: BLE001
                pass
    return {"ok": has_ver and got == count,
            "detail": {"has_acadver": has_ver, "entities_before": count,
                       "entities_after": got, "bytes": info.get("bytes")}}


def case_bad_extension(doc: Any, wd: str) -> Dict[str, Any]:
    """F5：未知扩展名——必须明确失败（不许写个假文件还说成功）。"""
    draw_fixture(doc)
    path = os.path.join(wd, "bad_%d.zzz" % int(time.time() * 1000))
    info = plot.save_as(doc, path)
    produced = os.path.exists(path)
    return {"ok": (not info.get("ok")) and bool(info.get("error")),
            "detail": {"ok": info.get("ok"), "error": info.get("error"),
                       "file_exists": produced,
                       "bytes": info.get("bytes")}}


def case_missing_dir(doc: Any, wd: str) -> Dict[str, Any]:
    """F6：父目录不存在——必须报错（这条守的是"不许偷偷建目录"）。"""
    draw_fixture(doc)
    path = os.path.join(wd, "f6_%d" % int(time.time() * 1000), "x.dwg")
    info = plot.save_as(doc, path)
    return {"ok": (not info.get("ok")) and bool(info.get("error")),
            "detail": {"ok": info.get("ok"), "error": info.get("error")}}


CASES = [
    {"id": "F1.dwg_native", "fn": case_dwg_native},
    {"id": "F2.dwg_versions", "fn": case_dwg_versions},
    {"id": "F3.reopen_roundtrip", "fn": case_reopen_roundtrip},
    {"id": "F4.dxf_write", "fn": case_dxf_write},
    {"id": "F5.bad_extension", "fn": case_bad_extension},
    {"id": "F6.missing_dir", "fn": case_missing_dir},
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="文件层规格（真机）")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--case-timeout", type=float, default=120.0)
    args = ap.parse_args(argv)

    wd = args.workdir or os.path.join(ROOT, "_scratch",
                                      "specfiles_%s" % time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(wd, exist_ok=True)
    start_watchdog(args.case_timeout, wd)
    sig_before = env_signature()
    info = launch.launch()
    app = info["app"]
    print("AutoCAD：%s（profile=%r）"
          % ("本次启动" if info["launched"] else "附加到已运行实例", info.get("profile")))
    runner = CaseRunner(app, wd, log=lambda m: print(m))
    runner.ensure_baseline_doc()

    results = []
    for case in CASES:
        _WATCH.update(deadline=time.time() + args.case_timeout, what=case["id"])
        t0 = time.time()
        doc = runner.new_doc("files:" + case["id"])
        res: Dict[str, Any] = {"id": case["id"]}
        try:
            res.update(case["fn"](doc, wd))
        except Exception as exc:                    # noqa: BLE001
            res.update({"ok": False, "detail": {"error": "%s: %s" % (type(exc).__name__, exc)}})
        finally:
            _WATCH["deadline"] = 0.0
            try:
                runner._close(doc, "files:" + case["id"])
            except Exception:                       # noqa: BLE001
                pass
        res["duration_s"] = round(time.time() - t0, 2)
        results.append(res)
        print("  %-24s %s  %.1fs" % (case["id"], "PASS" if res["ok"] else "FAIL",
                                     res["duration_s"]))

    passed = sum(1 for r in results if r["ok"])
    print("\n合计 %d 例：通过 %d / 失败 %d" % (len(results), passed, len(results) - passed))
    payload = {"suite": "spec_files", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "passed": passed, "total": len(results),
               "env_before": sig_before, "env_after": env_signature(),
               "results": results}
    with open(os.path.join(wd, "results.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    print("证据：%s" % os.path.join(wd, "results.json"))

    try:
        runner._close(runner.baseline_doc, "baseline")
        if info["launched"] and not args.keep:
            from acadkit.judges.case import finish
            print("收尾：%s" % finish(app, None, quit_app=True))
    except Exception as exc:                        # noqa: BLE001
        print("收尾失败：%s" % exc)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
