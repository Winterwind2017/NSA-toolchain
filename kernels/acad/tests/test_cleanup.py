"""重复实体（overkill）与未用对象（purge）的离线测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.dxf.cleanup import find_duplicates, find_unused, geo_key, overlaps  # noqa: E402
from acadkit.dxf.document import (Entity, add_entity, make_circle, make_line,   # noqa: E402
                                  new_document, read)


def test_identical_lines_are_duplicates() -> None:
    doc = new_document()
    add_entity(doc, make_line((0, 0), (40, 0), handle="1"))
    add_entity(doc, make_line((0, 0), (40, 0), handle="2"))
    add_entity(doc, make_circle((5, 5), 2, handle="3"))
    result = find_duplicates(doc)
    assert result["count"] == 1
    assert result["groups"][0] == ["1", "2"]
    assert result["removable"] == ["2"], "应保留最小句柄"


def test_reversed_line_is_duplicate() -> None:
    a = make_line((0, 0), (40, 0), handle="1")
    b = make_line((40, 0), (0, 0), handle="2")
    doc = new_document()
    add_entity(doc, a)
    add_entity(doc, b)
    assert find_duplicates(doc)["count"] == 1
    assert overlaps(a, b)


def test_near_but_not_equal_lines_are_kept_apart() -> None:
    doc = new_document()
    add_entity(doc, make_line((0, 0), (40, 0), handle="1"))
    add_entity(doc, make_line((0, 0.01), (40, 0), handle="2"))
    assert find_duplicates(doc)["count"] == 0


def test_unknown_entity_type_not_deduped() -> None:
    doc = new_document()
    add_entity(doc, Entity("MYSTERY", [(0, "MYSTERY"), (5, "1"), (10, "5")]))
    add_entity(doc, Entity("MYSTERY", [(0, "MYSTERY"), (5, "2"), (10, "5")]))
    assert find_duplicates(doc)["count"] == 0, "不认识的类型不敢去重"
    assert geo_key(Entity("MYSTERY", [(0, "MYSTERY")])) is None


def test_unused_layers_are_found() -> None:
    pairs = [
        (0, "SECTION"), (2, "TABLES"),
        (0, "TABLE"), (2, "LAYER"),
        (0, "LAYER"), (2, "0"), (62, "7"),
        (0, "LAYER"), (2, "USED"), (62, "1"),
        (0, "LAYER"), (2, "UNUSED"), (62, "2"),
        (0, "ENDTAB"), (0, "ENDSEC"),
        (0, "SECTION"), (2, "ENTITIES"),
        (0, "LINE"), (5, "1"), (8, "USED"), (10, "0"), (20, "0"), (11, "10"), (21, "0"),
        (0, "ENDSEC"), (0, "EOF"),
    ]
    import tempfile
    path = os.path.join(tempfile.mkdtemp(prefix="purge_"), "p.dxf")
    with open(path, "w", encoding="utf-8") as fh:
        for code, value in pairs:
            fh.write("%d\n%s\n" % (code, value))
    result = find_unused(read(path))
    assert result["layers"] == ["UNUSED"], result
    assert result["count"] >= 1


def test_unused_blocks_are_found() -> None:
    pairs = [
        (0, "SECTION"), (2, "BLOCKS"),
        (0, "BLOCK"), (2, "AA"), (0, "ENDBLK"),
        (0, "BLOCK"), (2, "BB"), (0, "ENDBLK"),
        (0, "ENDSEC"),
        (0, "SECTION"), (2, "ENTITIES"),
        (0, "INSERT"), (5, "1"), (8, "0"), (2, "AA"), (10, "0"), (20, "0"),
        (0, "ENDSEC"), (0, "EOF"),
    ]
    import tempfile
    path = os.path.join(tempfile.mkdtemp(prefix="purge2_"), "p.dxf")
    with open(path, "w", encoding="utf-8") as fh:
        for code, value in pairs:
            fh.write("%d\n%s\n" % (code, value))
    result = find_unused(read(path))
    assert result["blocks"] == ["BB"], result
