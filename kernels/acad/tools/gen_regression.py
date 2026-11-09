#!/usr/bin/env python3
"""把一次真机跑的 results.json 落成 `docs/regression/` 里的证据。

    python tools/gen_regression.py                       # 取 _scratch 里最新一次
    python tools/gen_regression.py --results <path>      # 指定
    python tools/gen_regression.py --name 2026-10-21     # 指定文件名

产物：
    docs/regression/<name>.json   完整 checks/detail（去掉 env 里重复的大字段）
    docs/regression/<name>.md     人读表格（族/级别/结果/耗时/关键数字）
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import caps               # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "regression")


def latest_results() -> str:
    paths = sorted(glob.glob(os.path.join(ROOT, "_scratch", "*", "results.json")))
    if not paths:
        raise SystemExit("_scratch 里没有 results.json，先跑 tests/live_judges.py")
    return paths[-1]


def trim(payload: dict) -> dict:
    out = dict(payload)
    out["results"] = []
    for r in payload.get("results") or []:
        detail = dict(r.get("detail") or {})
        env = dict(detail.get("env") or {})
        env.pop("variables_after", None)
        env.pop("case", None)
        detail["env"] = env
        out["results"].append({
            "id": r["id"], "family": r["family"], "title": r.get("title"),
            "ok": r["ok"], "duration_s": r.get("duration_s"),
            "negative": r.get("negative"),
            "checks": r.get("checks"),
            "detail": detail,
            "notes": r.get("notes"),
        })
    return out


def key_numbers(r: dict) -> str:
    d = r.get("detail") or {}
    bits = []
    for k in ("volume_read", "area", "length", "measurement_read",
              "pages", "size_mm", "size_pt", "blocks", "deltas", "attributes",
              "view_size", "dimtxt_read"):
        if k in d:
            v = d[k]
            if isinstance(v, dict):
                v = {kk: vv for kk, vv in list(v.items())[:4]}
            if isinstance(v, list):
                v = v[:4]
            bits.append("%s=%s" % (k, json.dumps(v, ensure_ascii=False)[:80]))
        if len(bits) >= 3:
            break
    return "；".join(bits) if bits else "-"


def render_md(payload: dict, name: str) -> str:
    results = payload.get("results") or []
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    env_ok = sum(1 for r in results for k, v in (r.get("checks") or {}).items()
                 if k.startswith("env_") and v is True)
    env_total = sum(1 for r in results for k in (r.get("checks") or {})
                    if k.startswith("env_"))
    lines = [
        "# 真机回归 %s" % name,
        "",
        "> 由 `python tools/gen_regression.py` 生成；原始 JSON 是同目录的 "
        "`%s.json`。" % name,
        "",
        "- 生成时间：%s" % payload.get("generated_at"),
        "- AutoCAD：%s" % json.dumps(payload.get("autocad") or {}, ensure_ascii=False),
        "- 环境指纹：跑前 %s → 跑后 %s"
        % (json.dumps(payload.get("env_before") or {}, ensure_ascii=False),
           json.dumps(payload.get("env_after") or {}, ensure_ascii=False)),
        "- 结果：**%d / %d 通过**；环境自检 %d / %d 项通过"
        % (passed, total, env_ok, env_total),
        "",
        "| 族 | 用例 | 级别 | 结果 | 耗时 | 关键数字 |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        cap = caps.BY_ID.get(r["id"])
        lines.append("| %s | `%s` | %s | %s | %.1fs | %s |"
                     % (r["family"], r["id"], cap.level if cap else "-",
                        "PASS" if r["ok"] else "**FAIL**",
                        r.get("duration_s") or 0.0, key_numbers(r)))
    lines += ["", "## 失败项（如果有）", ""]
    bad = [r for r in results if not r["ok"]]
    if not bad:
        lines.append("无。")
    else:
        for r in bad:
            failed = [k for k, v in (r.get("checks") or {}).items() if v is False]
            lines.append("- `%s`：%s" % (r["id"], ", ".join(failed)))
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把真机结果落成回归证据")
    ap.add_argument("--results", default=None)
    ap.add_argument("--name", default=None)
    args = ap.parse_args(argv)
    path = args.results or latest_results()
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    name = args.name or time.strftime("%Y-%m-%d_%H%M")
    os.makedirs(OUT_DIR, exist_ok=True)
    json_path = os.path.join(OUT_DIR, name + ".json")
    md_path = os.path.join(OUT_DIR, name + ".md")
    with open(json_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(trim(payload), fh, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_md(payload, name))
    print("已写 %s" % os.path.relpath(json_path, ROOT))
    print("已写 %s" % os.path.relpath(md_path, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
