"""图纸自检（AUDIT 的离线替代）测试。"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.dxf.audit import audit, report_text                    # noqa: E402
from acadkit.dxf.document import (Entity, add_entity, make_circle,  # noqa: E402
                                  make_line, new_document, read, write)


def _rules(result) -> list:
    return [i["rule"] for i in result["issues"]]


def test_clean_document_passes() -> None:
    doc = new_document()
    add_entity(doc, make_line((0, 0), (40, 0), handle="1"))
    add_entity(doc, make_circle((10, 10), 5, handle="2"))
    result = audit(doc)
    assert result["ok"], result["issues"]
    assert result["entities"] == 2


def test_duplicate_handle_detected() -> None:
    doc = new_document()
    add_entity(doc, make_line((0, 0), (10, 0), handle="7"))
    add_entity(doc, make_circle((0, 0), 2, handle="7"))
    result = audit(doc)
    assert "duplicate_handle" in _rules(result)
    assert not result["ok"]


def test_non_finite_coordinates_detected() -> None:
    doc = new_document()
    add_entity(doc, Entity("LINE", [(0, "LINE"), (5, "1"), (8, "0"),
                                    (10, "nan"), (20, "0.0"), (11, "10.0"), (21, "0.0")]))
    result = audit(doc)
    assert "non_finite_coord" in _rules(result)
    assert not result["ok"]


def test_zero_length_line_and_bad_radius() -> None:
    doc = new_document()
    add_entity(doc, make_line((5, 5), (5, 5), handle="1"))
    add_entity(doc, make_circle((0, 0), 0.0, handle="2"))
    rules = _rules(audit(doc))
    assert "zero_length_line" in rules
    assert "bad_radius" in rules


def test_unknown_layer_warn_only() -> None:
    """有图层表但实体引用了不存在的图层 → warn，不算 error。"""
    pairs = [
        (0, "SECTION"), (2, "TABLES"),
        (0, "TABLE"), (2, "LAYER"),
        (0, "LAYER"), (2, "0"), (62, "7"),
        (0, "ENDTAB"), (0, "ENDSEC"),
        (0, "SECTION"), (2, "ENTITIES"),
        (0, "LINE"), (5, "1"), (8, "GHOST"), (10, "0"), (20, "0"),
        (11, "10"), (21, "0"),
        (0, "ENDSEC"), (0, "EOF"),
    ]
    path = os.path.join(tempfile.mkdtemp(prefix="audit_"), "a.dxf")
    with open(path, "w", encoding="utf-8") as fh:
        for code, value in pairs:
            fh.write("%d\n%s\n" % (code, value))
    result = audit(read(path))
    assert "unknown_layer" in _rules(result)
    assert result["ok"], "只应告警，不应判失败"
    assert result["counts"].get("warn") == 1


def test_polyline_mismatch_and_duplicate_vertex() -> None:
    doc = new_document()
    add_entity(doc, Entity("LWPOLYLINE", [(0, "LWPOLYLINE"), (5, "3"), (8, "0"),
                                          (90, "3"),
                                          (10, "0"), (20, "0"),
                                          (10, "0"), (20, "0"),
                                          (10, "10"), (20, "0")]))
    assert "duplicate_vertex" in _rules(audit(doc))

    doc2 = new_document()
    add_entity(doc2, Entity("LWPOLYLINE", [(0, "LWPOLYLINE"), (5, "4"), (8, "0"),
                                           (10, "0"), (20, "0"), (10, "10")]))
    assert "polyline_xy_mismatch" in _rules(audit(doc2))


def test_text_height_must_be_positive() -> None:
    doc = new_document()
    add_entity(doc, Entity("TEXT", [(0, "TEXT"), (5, "5"), (8, "0"),
                                    (10, "0"), (20, "0"), (40, "0"), (1, "ABC")]))
    assert "bad_text_height" in _rules(audit(doc))


def test_missing_handle_is_info() -> None:
    doc = new_document()
    add_entity(doc, Entity("POINT", [(0, "POINT"), (8, "0"), (10, "1"), (20, "2")]))
    result = audit(doc)
    assert "missing_handle" in _rules(result)
    assert result["ok"], "缺句柄只是提示"


def test_report_text_is_readable() -> None:
    doc = new_document()
    add_entity(doc, make_line((0, 0), (0, 0), handle="9"))
    text = report_text(audit(doc))
    assert "实体 1" in text and "zero_length_line" in text


def test_audit_on_written_file() -> None:
    """存盘→再读→自检，确认结论一致（文件层与内存层等价）。"""
    doc = new_document()
    add_entity(doc, make_circle((0, 0), 0.0, handle="A"))
    path = os.path.join(tempfile.mkdtemp(prefix="audit2_"), "b.dxf")
    write(doc, path)
    result = audit(read(path))
    assert "bad_radius" in _rules(result)
