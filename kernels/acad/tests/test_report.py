"""报告流水线端到端测试：一次求解 → 云图 + 图纸 + STEP/STL + report.md/json。

判据（都是文件级、可复核）：退出码、report.json 里的 checks 全 True、
report.md 含关键小节、无零件工况不产出图纸。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "tools", "report.py")

try:
    from acadkit.brep import parts as B          # noqa: F401
    has_brep = True
except Exception:                                # noqa: BLE001
    has_brep = False

try:
    from acadkit.fea import runner as R
    has_ccx = R.find_ccx() is not None
except Exception:                                # noqa: BLE001
    has_ccx = False

need = pytest.mark.skipif(not (has_brep and has_ccx), reason="缺 brep 或 ccx")


def _run(*args) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, TOOL] + list(args), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          env=env, timeout=1800)


@need
def test_report_brep_case_produces_all_artifacts() -> None:
    d = tempfile.mkdtemp(prefix="rep_")
    res = _run("--case", "brep-cantilever", "--part", "plate",
               "--length", "200", "--width", "100", "--thickness", "8",
               "--force", "100", "--title", "支架校核", "--number", "NSA-100",
               "--material", "Q235B", "--outdir", d, "--no-viewer")
    assert res.returncode == 0, res.stdout + res.stderr

    for fn in ("report.md", "report.json", "deformed.png", "drawing.pdf",
               "part.step", "part.stl"):
        assert os.path.isfile(os.path.join(d, fn)), fn

    payload = json.load(open(os.path.join(d, "report.json"), encoding="utf-8"))
    assert payload["checks"]["physics_ok"] is True
    assert payload["checks"]["png_ok"] is True
    assert payload["checks"]["drawing_ok"] is True
    assert "viewer_ok" not in payload["checks"], "--no-viewer 时不该有 viewer 判据"

    md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
    for token in ("# 校核报告", "## 1 工况与参数", "## 2 判据", "相对误差",
                  "## 4 产物", "## 6 边界与假设", "screening"):
        assert token in md, token
    assert open(os.path.join(d, "deformed.png"), "rb").read(8) == b"\x89PNG\r\n\x1a\n"
    assert open(os.path.join(d, "drawing.pdf"), "rb").read(5) == b"%PDF-"


@need
def test_report_without_part_skips_drawing() -> None:
    d = tempfile.mkdtemp(prefix="rep2_")
    res = _run("--case", "bar", "--length", "100", "--width", "10", "--height", "10",
               "--force", "10000", "--nu", "0", "--outdir", d, "--no-viewer")
    assert res.returncode == 0, res.stdout + res.stderr
    assert os.path.isfile(os.path.join(d, "deformed.png"))
    assert not os.path.isfile(os.path.join(d, "drawing.pdf")), "无零件时不该有图纸"

    payload = json.load(open(os.path.join(d, "report.json"), encoding="utf-8"))
    assert payload["checks"]["physics_ok"] is True
    assert "drawing_ok" not in payload["checks"]
    md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
    assert "结论：**通过**" in md


def test_report_rejects_unsupported_case() -> None:
    for case in ("render", "sweep", "flange"):
        res = _run("--case", case, "--outdir", tempfile.mkdtemp(prefix="rep3_"))
        assert res.returncode == 2, (case, res.stdout, res.stderr)
        assert "report 不支持" in res.stderr


@need
def test_report_fails_when_physics_fails() -> None:
    """容差故意给成 1e-12，物理判据必须失败、退出码非 0（不能假通过）。"""
    d = tempfile.mkdtemp(prefix="rep4_")
    res = _run("--case", "brep-cantilever", "--part", "plate",
               "--length", "200", "--width", "100", "--thickness", "8",
               "--force", "100", "--tol", "1e-12", "--outdir", d,
               "--no-viewer", "--no-drawing")
    assert res.returncode == 1, res.stdout + res.stderr
    payload = json.load(open(os.path.join(d, "report.json"), encoding="utf-8"))
    assert payload["checks"]["physics_ok"] is False
    md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
    assert "结论：**未通过**" in md
