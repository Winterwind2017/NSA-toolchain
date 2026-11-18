"""DXF 读写 + 格式探测 + 无损差异的离线测试。"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.dxf.document import (DxfError, Entity, add_entity, make_circle,  # noqa: E402
                                  make_line, new_document, read, write)
from acadkit.dxf.io import SniffError, diff_documents, sniff                     # noqa: E402


def _tmp(name: str) -> str:
    d = tempfile.mkdtemp(prefix="acadkit_dxf_")
    return os.path.join(d, name)


def test_new_document_roundtrip() -> None:
    doc = new_document()
    add_entity(doc, make_line((0, 0), (40, 0), handle="AA"))
    add_entity(doc, make_circle((10, 5), 3.5, handle="AB"))
    path = _tmp("a.dxf")
    info = write(doc, path)
    assert info["bytes"] > 100

    back = read(path)
    assert back.acadver() == "AC1032"
    ents = back.entities()
    assert [e.type for e in ents] == ["LINE", "CIRCLE"]
    assert ents[0].point() == (0.0, 0.0, 0.0)
    assert ents[1].floats(40)[0] == 3.5
    assert {e.handle for e in ents} == {"AA", "AB"}


def test_unknown_entity_is_preserved_verbatim() -> None:
    """未知实体必须原样保留——这是"读别人的图"的底线。"""
    doc = new_document()
    weird = Entity("MYSTERY_THING", [(0, "MYSTERY_THING"), (5, "FF"), (8, "层1"),
                                     (999, "anything goes"), (70, "42")])
    add_entity(doc, weird)
    path = _tmp("b.dxf")
    write(doc, path)
    back = read(path)
    got = [e for e in back.entities() if e.type == "MYSTERY_THING"]
    assert len(got) == 1
    assert got[0].pairs == weird.pairs, "未知实体被改写/丢弃了"


def test_roundtrip_preserves_all_pairs() -> None:
    doc = new_document()
    add_entity(doc, make_line((1, 2), (3, 4), layer="OUTLINE", handle="1"))
    p1 = _tmp("c1.dxf")
    write(doc, p1)
    d1 = read(p1)
    p2 = _tmp("c2.dxf")
    write(d1, p2)
    d2 = read(p2)
    assert d1.pairs == d2.pairs, "二次往返应完全一致"


def test_layers_are_read() -> None:
    pairs = [
        (0, "SECTION"), (2, "TABLES"),
        (0, "TABLE"), (2, "LAYER"),
        (0, "LAYER"), (2, "OUTLINE"), (62, "7"), (6, "CONTINUOUS"),
        (0, "LAYER"), (2, "HIDDEN"), (62, "8"), (6, "DASHED"),
        (0, "ENDTAB"), (0, "ENDSEC"),
        (0, "SECTION"), (2, "ENTITIES"), (0, "ENDSEC"), (0, "EOF"),
    ]
    path = _tmp("layers.dxf")
    with open(path, "w", encoding="utf-8") as fh:
        for code, value in pairs:
            fh.write("%d\n%s\n" % (code, value))
    doc = read(path)
    layers = doc.layers()
    assert layers["OUTLINE"]["color"] == "7"
    assert layers["HIDDEN"]["linetype"] == "DASHED"


def test_malformed_odd_lines_raises() -> None:
    path = _tmp("bad.dxf")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("0\nSECTION\n2\nENTITIES\n")     # 缺 ENDSEC/EOF，成对但结构不完整
    doc = read(path)                               # 结构不完整不崩，读成空 ENTITIES
    assert doc.entities() == []
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("0\nSECTION\n2\n")               # 奇数行
    try:
        read(path)
    except DxfError as exc:
        assert "奇数" in str(exc)
    else:
        raise AssertionError("奇数行应抛 DxfError")


def test_bad_group_code_raises() -> None:
    path = _tmp("badcode.dxf")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("XX\nSECTION\n")
    try:
        read(path)
    except DxfError as exc:
        assert "组码" in str(exc)
    else:
        raise AssertionError("非数字组码应抛 DxfError")


def test_binary_dxf_rejected() -> None:
    path = _tmp("bin.dxf")
    with open(path, "wb") as fh:
        fh.write(b"AutoCAD Binary DXF\r\n\x1a\x00")
    try:
        read(path)
    except DxfError as exc:
        assert "二进制" in str(exc)
    else:
        raise AssertionError("二进制 DXF 应被拒绝")


def test_write_missing_dir_raises() -> None:
    doc = new_document()
    try:
        write(doc, os.path.join(tempfile.gettempdir(), "no_such_xyz", "a.dxf"))
    except DxfError as exc:
        assert "父目录" in str(exc)
    else:
        raise AssertionError("缺父目录应抛 DxfError")


def test_sniff_formats() -> None:
    dxf = _tmp("s.dxf")
    write(new_document(), dxf)
    assert sniff(dxf)["format"] == "dxf"

    pdf = _tmp("s.pdf")
    with open(pdf, "wb") as fh:
        fh.write(b"%PDF-1.7\n...")
    assert sniff(pdf)["format"] == "pdf"

    dwg = _tmp("s.dwg")
    with open(dwg, "wb") as fh:
        fh.write(b"AC1032\x00\x00")
    assert sniff(dwg)["format"] == "dwg"

    step = _tmp("s.step")
    with open(step, "wb") as fh:
        fh.write(b"ISO-10303-21;\n")
    assert sniff(step)["format"] == "step"

    junk = _tmp("s.bin")
    with open(junk, "wb") as fh:
        fh.write(b"\x00\x01\x02")
    assert sniff(junk)["format"] == "unknown"

    try:
        sniff(os.path.join(tempfile.gettempdir(), "definitely_missing_zzz"))
    except SniffError:
        pass
    else:
        raise AssertionError("不存在的文件应抛 SniffError")


def test_diff_detects_lost_entities() -> None:
    """模拟"保存丢了东西"：新文件少一个实体、改了一个。"""
    old = new_document()
    add_entity(old, make_line((0, 0), (10, 0), handle="1"))
    add_entity(old, make_circle((5, 5), 2, handle="2"))
    new = new_document()
    add_entity(new, make_line((0, 0), (10, 0), handle="1"))
    add_entity(new, make_circle((5, 5), 2.5, handle="2"))   # 半径改了

    rep = diff_documents(old, new)
    assert rep.removed == [] and rep.added == []
    assert rep.changed == ["h:2"], rep.changed

    lost = new_document()
    add_entity(lost, make_line((0, 0), (10, 0), handle="1"))
    rep2 = diff_documents(old, lost)
    assert rep2.removed == ["h:2"] and rep2.lost == 1
