"""离线图纸测试：投影 / 三视图 PDF / 幅面与文字复核 / CLI。

判据都是独立可复核的：PDF 头、pypdf 读页数与幅面（mm）、标题栏文字能提取、
可见/隐藏线框段数、比例落在标准序列。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

try:
    from acadkit.brep import drawing as D
    from acadkit.brep import parts as B
    has_brep = True
except Exception:                                     # noqa: BLE001
    has_brep = False

need = pytest.mark.skipif(not has_brep, reason="缺 cadquery")

try:
    import pypdf                                   # noqa: F401
    has_pypdf = True
except Exception:                                     # noqa: BLE001
    has_pypdf = False


def _flange():
    return B.flange(outer_d=120, bore_d=40, thickness=10,
                    bolt_holes=[{"diameter": 10, "bcd": 90, "count": 4}])


# ── 投影 ──────────────────────────────────────────────────────────
@need
def test_project_has_visible_and_hidden() -> None:
    pr = D.project(_flange(), "front")
    assert pr["counts"]["visible"] > 0
    assert pr["counts"]["hidden"] > 0, "带孔件侧视应有隐藏线"
    x0, y0, x1, y1 = pr["bbox"]
    assert x1 > x0 and y1 > y0


@need
def test_project_rejects_unknown_view() -> None:
    with pytest.raises(Exception) as ei:
        D.project(_flange(), "back")
    assert "未知视角" in str(ei.value)


@need
def test_project_rejects_non_part() -> None:
    with pytest.raises(Exception):
        D.project(object(), "front")


# ── 三视图 PDF ────────────────────────────────────────────────────
@need
def test_sheet_pdf_a3_is_vector_with_titleblock() -> None:
    d = tempfile.mkdtemp(prefix="drw_")
    path = os.path.join(d, "a3.pdf")
    st = D.sheet_pdf(_flange(), path, sheet="A3",
                     title_block={"title": "法兰盘", "number": "NSA-001",
                                  "material": "Q235B"})
    assert open(path, "rb").read(5) == b"%PDF-"
    assert st["bytes"] > 5000
    assert st["segments_visible"] > 0
    assert st["page_mm"] == pytest.approx([420.0, 297.0], abs=1.5)
    assert st["scale"] in D.STD_SCALES
    assert st["page_size_ok"] is True
    assert st["text_ok"] is True, st.get("missing_text")
    if has_pypdf:
        assert st["pages"] == 1


@need
def test_sheet_pdf_a4_single_view() -> None:
    d = tempfile.mkdtemp(prefix="drw2_")
    st = D.sheet_pdf(B.plate(length=200, width=100, thickness=12),
                     os.path.join(d, "a4.pdf"), sheet="A4", views=("front",))
    assert st["page_mm"] == pytest.approx([297.0, 210.0], abs=1.5)
    assert st["views"] == ["front"]


@need
def test_sheet_pdf_chinese_labels_and_fallback_flag() -> None:
    d = tempfile.mkdtemp(prefix="drw3_")
    st = D.sheet_pdf(_flange(), os.path.join(d, "f.pdf"))
    assert st["chinese_labels"] is True or st["chinese_labels"] is False
    # 有中文字体时标签用中文；没有则英文，但都必须如实上报
    if st["chinese_labels"]:
        assert st["font"]


@need
def test_sheet_pdf_rejects_bad_args() -> None:
    d = tempfile.mkdtemp(prefix="drw4_")
    with pytest.raises(Exception) as ei:
        D.sheet_pdf(_flange(), os.path.join(d, "x.pdf"), sheet="B5")
    assert "未知图幅" in str(ei.value)
    with pytest.raises(Exception) as ei2:
        D.sheet_pdf(_flange(), os.path.join(d, "y.pdf"), views=())
    assert "不能为空" in str(ei2.value)
    with pytest.raises(Exception) as ei3:
        D.sheet_pdf(_flange(), os.path.join(d, "no_dir", "z.pdf"))
    assert "父目录" in str(ei3.value)


def test_verify_pdf_rejects_non_pdf() -> None:
    d = tempfile.mkdtemp(prefix="drw5_")
    p = os.path.join(d, "fake.pdf")
    open(p, "wb").write(b"not a pdf at all")
    with pytest.raises(Exception) as ei:
        D.verify_pdf(p)
    assert "PDF 头" in str(ei.value)


# ── CLI ───────────────────────────────────────────────────────────
@need
def test_cli_writes_pdf_and_exits_zero() -> None:
    d = tempfile.mkdtemp(prefix="drwcli_")
    out = os.path.join(d, "cli.pdf")
    tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "tools", "drawing.py")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run([sys.executable, tool, "--part", "plate", "--length", "160",
                          "--width", "90", "--thickness", "10", "--title", "底板",
                          "--number", "NSA-100", "--material", "Q235B",
                          "--sheet", "A3", "--pdf", out],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", env=env, timeout=600)
    assert res.returncode == 0, res.stdout + res.stderr
    assert os.path.isfile(out) and os.path.getsize(out) > 5000
    assert "幅面复核：过" in res.stdout
