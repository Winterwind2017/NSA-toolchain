"""字宽估算与 DWG 结构读取的离线测试。"""

from __future__ import annotations

import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit import textmetrics as TM                                  # noqa: E402
from acadkit.dwg.header import DwgError, read_header, summary_text     # noqa: E402


# ── 字宽估算 ────────────────────────────────────────────────────────
def test_char_widths_are_ordered() -> None:
    assert TM.char_width_units("i") < TM.char_width_units("m")
    assert TM.char_width_units("0") < TM.char_width_units("字")
    assert TM.char_width_units(" ") > 0


def test_text_width_scales_with_height() -> None:
    w1 = TM.text_width("ACADKIT", 2.5)
    w2 = TM.text_width("ACADKIT", 5.0)
    assert abs(w2 - 2 * w1) < 1e-9


def test_width_factor_and_validation() -> None:
    base = TM.text_width("ABC", 10)
    assert abs(TM.text_width("ABC", 10, width_factor=0.8) - 0.8 * base) < 1e-9
    for kwargs in ({"height": 0}, {"height": 5, "width_factor": 0}):
        try:
            TM.text_width("A", **kwargs)
        except ValueError:
            continue
        raise AssertionError("非法参数应报错：%r" % kwargs)


def test_mtext_width_and_height() -> None:
    info = TM.mtext_width("第一行\n第二行更长一些", 3.5, line_spacing=1.5)
    assert info["height"] == 3.5 * 1.5 * 2
    assert info["width"] > 0


def test_overlap_detection() -> None:
    boxes = [{"x": 0, "y": 0, "w": 10, "h": 5},
             {"x": 5, "y": 2, "w": 10, "h": 5},
             {"x": 100, "y": 0, "w": 10, "h": 5}]
    assert TM.fits_without_overlap(boxes) == [(0, 1)]


def test_estimate_layout_boxes() -> None:
    boxes = TM.estimate_layout([{"text": "ABC", "x": 0, "y": 0},
                                {"text": "很长的中文标题", "x": 0, "y": 20}], height=3)
    assert boxes[0]["h"] == 3.75
    assert boxes[1]["w"] > boxes[0]["w"]


# ── DWG 结构 ────────────────────────────────────────────────────────
def _fake_dwg(path: str, *, version: str = "AC1032", maintenance: int = 4,
              sections: list = None, size: int = 4096) -> str:
    sections = sections or [(0, 0x100, 400), (1, 0x300, 200),
                            (2, 0x400, 1000), (3, 0, 0), (4, 0, 0), (5, 0, 0)]
    buf = bytearray(size)
    buf[0:6] = version.encode("latin-1")
    buf[6] = maintenance
    pos = 0x15
    for num, off, ln in sections:
        struct.pack_into("<BII", buf, pos, num, off, ln)
        pos += 9 + 2
    with open(path, "wb") as fh:
        fh.write(bytes(buf))
    return path


def test_read_real_structure() -> None:
    d = tempfile.mkdtemp(prefix="dwg_")
    path = _fake_dwg(os.path.join(d, "a.dwg"))
    h = read_header(path)
    assert h.version == "AC1032" and h.release == "2018+"
    assert h.maintenance == 4 and h.size == 4096
    assert [s.number for s in h.sections] == [0, 1, 2, 3, 4, 5]
    assert "header_vars" in [s.name for s in h.sections]
    assert h.ok, h.problems
    assert "段表自洽" in summary_text(h)


def test_rejects_non_dwg() -> None:
    d = tempfile.mkdtemp(prefix="dwg2_")
    p = os.path.join(d, "x.bin")
    with open(p, "wb") as fh:
        fh.write(b"%PDF-1.7")
    try:
        read_header(p)
    except DwgError as exc:
        assert "不是 DWG" in str(exc)
    else:
        raise AssertionError("非 DWG 应报错")


def test_rejects_truncated() -> None:
    d = tempfile.mkdtemp(prefix="dwg3_")
    p = os.path.join(d, "short.dwg")
    with open(p, "wb") as fh:
        fh.write(b"AC1032" + b"\x00" * 8)
    try:
        read_header(p)
    except DwgError as exc:
        assert "截断" in str(exc)
    else:
        raise AssertionError("截断文件应报错")


def test_detects_section_beyond_eof() -> None:
    d = tempfile.mkdtemp(prefix="dwg4_")
    p = _fake_dwg(os.path.join(d, "b.dwg"),
                  sections=[(0, 0x100, 400), (1, 0x300, 200),
                            (2, 4000, 9999), (3, 0, 0), (4, 0, 0), (5, 0, 0)])
    h = read_header(p)
    assert not h.ok
    assert any("越界" in x for x in h.problems)


def test_detects_overlapping_sections() -> None:
    d = tempfile.mkdtemp(prefix="dwg5_")
    p = _fake_dwg(os.path.join(d, "c.dwg"),
                  sections=[(0, 0x100, 0x400), (1, 0x200, 0x100),
                            (2, 0x400, 0x100), (3, 0, 0), (4, 0, 0), (5, 0, 0)])
    h = read_header(p)
    assert not h.ok and any("重叠" in x for x in h.problems)


def test_unparsable_layout_is_refused_not_faked() -> None:
    """段表不像 R13 布局时必须报"无法解析"，绝不输出假段表。"""
    d = tempfile.mkdtemp(prefix="dwg7_")
    p = os.path.join(d, "weird.dwg")
    buf = bytearray(2048)
    buf[0:6] = b"AC1032"
    buf[0x15:0x15 + 66] = bytes(range(11, 77))       # 故意放垃圾
    with open(p, "wb") as fh:
        fh.write(bytes(buf))
    h = read_header(p)
    assert not h.ok
    assert h.sections == [], "解析不了就不该给段表"
    assert any("无法按 R13 布局解析" in x for x in h.problems)


def test_unknown_version_is_flagged_not_fatal() -> None:
    d = tempfile.mkdtemp(prefix="dwg6_")
    p = _fake_dwg(os.path.join(d, "d.dwg"), version="AC1099")
    h = read_header(p)
    assert h.release is None
    assert any("未知版本" in x for x in h.problems)
