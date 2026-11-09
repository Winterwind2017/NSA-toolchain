"""判据离线测试：不需要 AutoCAD。

真机用例（tests/live_judges.py）证明"在本机能把东西做对"；这里证明另一半：
**判据真的会失败**。`docs/JUDGE_SPEC.md` 第四节说得很直接：

    不能失败的判据，通常也证明不了成功。

所以每个判据既有"正例通过"，也有"改一个数/少一个属性/少一次重开就必须失败"。
"""

from __future__ import annotations

import json
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acadkit import registry                                     # noqa: E402
from acadkit.judges import dxfinfo, pdfinfo                 # noqa: E402
from acadkit.judges import block_table as bt                     # noqa: E402
from acadkit.judges import dim, export, geom                     # noqa: E402
from acadkit.judges.base import (Drawing, Entity, JudgeError,     # noqa: E402
                                 Readback, verdict)


# ── 构造读回 ────────────────────────────────────────────────────────
def E(handle: str, type_name: str, **attrs) -> Entity:
    return Entity(handle=handle, type=type_name, attrs=dict(attrs))


def D(source: str, entities, insunits: int = 4, meta=None) -> Drawing:
    return Drawing(source=source, insunits=insunits,
                   entities=list(entities), meta=meta or {})


def rb(before, memory, reopened=None, dxf=None, dxf_reopened=None) -> Readback:
    return Readback(before=before, memory=memory, reopened=reopened,
                    dxf=dxf, dxf_reopened=dxf_reopened)


def circle(handle="A1", center=(10.0, 20.0, 0.0), radius=25.0, area=None):
    return E(handle, "CIRCLE", ObjectName="AcDbCircle", Center=list(center),
             Radius=radius, Area=area if area is not None else 3.141592653589793 * radius ** 2)


# ── 收口约定 ────────────────────────────────────────────────────────
def test_verdict_ok_is_all_checks() -> None:
    res = verdict({"a": True, "b": True}, {"n": 1})
    assert res["ok"] is True and res["detail"]["n"] == 1
    res = verdict({"a": True, "b": False}, {})
    assert res["ok"] is False
    assert res["checks"] == {"a": True, "b": False}


def test_verdict_rejects_none_and_empty() -> None:
    with pytest.raises(JudgeError):
        verdict({"a": None})                       # type: ignore[dict-item]
    with pytest.raises(JudgeError):
        verdict({})


def test_every_judge_result_has_contract_keys() -> None:
    """所有判据的返回形状一致，且 ok==all(checks)。"""
    res = geom.judge_circle(rb(D("before", []), D("memory", [circle()]), D("reopened", [circle()])),
                            center=(10, 20, 0), radius=25.0)
    assert set(res) == {"ok", "checks", "detail", "raw"}
    assert res["ok"] is all(res["checks"].values())


# ── geom ────────────────────────────────────────────────────────────
_UNSET = object()


def _circle_rb(memory=None, reopened=_UNSET, before=None):
    return rb(before or D("before", []),
              memory if memory is not None else D("memory", [circle()]),
              D("reopened", []) if reopened is None else
              (D("reopened", [circle()]) if reopened is _UNSET else reopened))


def test_circle_pass_and_detail_is_checkable() -> None:
    res = geom.judge_circle(_circle_rb(), center=(10, 20, 0), radius=25.0)
    assert res["ok"], res
    assert res["detail"]["radius_du"] == 25.0
    assert res["detail"]["radius_mm"] == 25.0          # INSUNITS=4
    assert abs(res["detail"]["area_du2"] - 3.141592653589793 * 625) < 1e-6


def test_circle_fails_on_wrong_radius() -> None:
    res = geom.judge_circle(_circle_rb(memory=D("memory", [circle(radius=24.0)])),
                            center=(10, 20, 0), radius=25.0)
    assert res["ok"] is False
    assert res["checks"]["geometry"] is False


def test_circle_fails_without_reopen() -> None:
    res = geom.judge_circle(_circle_rb(reopened=None), center=(10, 20, 0), radius=25.0)
    assert res["ok"] is False and res["checks"]["reopen"] is False


def test_circle_fails_when_reopened_radius_changed() -> None:
    res = geom.judge_circle(
        _circle_rb(reopened=D("reopened", [circle(radius=26.0)])),
        center=(10, 20, 0), radius=25.0)
    assert res["checks"]["reopen"] is False


def test_circle_fails_when_area_inconsistent() -> None:
    res = geom.judge_circle(_circle_rb(memory=D("memory", [circle(area=1.0)])),
                            center=(10, 20, 0), radius=25.0)
    assert res["checks"]["area"] is False


def test_line_pass_and_fail() -> None:
    line = E("L1", "LINE", ObjectName="AcDbLine",
             StartPoint=[0.0, 0.0, 0.0], EndPoint=[60.0, 0.0, 0.0], Length=60.0)
    good = rb(D("before", []), D("memory", [line]), D("reopened", [line]))
    assert geom.judge_line(good, start=(0, 0, 0), end=(60, 0, 0))["ok"]
    bad = rb(D("before", []),
             D("memory", [E("L1", "LINE", ObjectName="AcDbLine",
                            StartPoint=[0.0, 0.0, 0.0], EndPoint=[61.0, 0.0, 0.0],
                            Length=61.0)]), D("reopened", []))
    assert geom.judge_line(bad, start=(0, 0, 0), end=(60, 0, 0))["ok"] is False


def test_rect_pass_and_vertex_mismatch_fails() -> None:
    verts = [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0]]
    pl = E("P1", "LWPOLYLINE", ObjectName="AcDbPolyline", Closed=True,
           Area=1200.0, Length=140.0, vertices=verts)
    good = rb(D("before", []), D("memory", [pl]), D("reopened", [pl]))
    res = geom.judge_rect(good, corner1=(0, 0), corner2=(40, 30))
    assert res["ok"], res

    skew = E("P1", "LWPOLYLINE", ObjectName="AcDbPolyline", Closed=True,
             Area=1200.0, Length=140.0,
             vertices=[[0.0, 0.0], [40.0, 0.0], [40.0, 29.0], [0.0, 30.0]])
    bad = rb(D("before", []), D("memory", [skew]), D("reopened", [skew]))
    assert geom.judge_rect(bad, corner1=(0, 0), corner2=(40, 30))["ok"] is False


# ── dim ─────────────────────────────────────────────────────────────
def _dim(type_name: str, handle="D1", measurement=60.0, text_pos=(30.0, 11.875, 0.0)):
    return E(handle, type_name, ObjectName="AcDb" + type_name.title().replace("Dimension", "Dimension"),
             Measurement=measurement, TextPosition=list(text_pos))


def test_linear_dim_pass() -> None:
    ent = E("D1", "ROTATEDDIMENSION", ObjectName="AcDbRotatedDimension",
            Measurement=60.0, TextPosition=[30.0, 11.875, 0.0])
    res = dim.judge_linear(rb(D("b", []), D("m", [ent]), D("r", [ent])),
                           p1=(0, 0), p2=(60, 0), dim_line=(30, 10), expected=60.0)
    assert res["ok"], res
    assert res["detail"]["measurement_du"] == 60.0


def test_linear_dim_wrong_measurement_fails() -> None:
    ent = E("D1", "ROTATEDDIMENSION", ObjectName="AcDbRotatedDimension",
            Measurement=59.0, TextPosition=[30.0, 11.875, 0.0])
    res = dim.judge_linear(rb(D("b", []), D("m", [ent]), D("r", [ent])),
                           p1=(0, 0), p2=(60, 0), dim_line=(30, 10), expected=60.0)
    assert res["checks"]["measurement"] is False


def test_linear_dim_text_on_wrong_side_fails() -> None:
    ent = E("D1", "ROTATEDDIMENSION", ObjectName="AcDbRotatedDimension",
            Measurement=60.0, TextPosition=[30.0, -5.0, 0.0])
    res = dim.judge_linear(rb(D("b", []), D("m", [ent]), D("r", [ent])),
                           p1=(0, 0), p2=(60, 0), dim_line=(30, 10), expected=60.0)
    assert res["checks"]["text_side"] is False


def test_diametric_dim_uses_diameter() -> None:
    ent = E("D1", "DIAMETRICDIMENSION", ObjectName="AcDbDiametricDimension",
            Measurement=50.0, TextPosition=[43.75, 20.0, 0.0])
    assert dim.judge_diametric(rb(D("b", []), D("m", [ent]), D("r", [ent])),
                               radius=25.0)["ok"]
    ent2 = E("D1", "DIAMETRICDIMENSION", ObjectName="AcDbDiametricDimension",
             Measurement=25.0, TextPosition=[43.75, 20.0, 0.0])
    res = dim.judge_diametric(rb(D("b", []), D("m", [ent2]), D("r", [ent2])),
                              radius=25.0)
    assert res["checks"]["measurement"] is False


def test_judge_raised_negative_control() -> None:
    assert dim.judge_raised(None)["ok"] is False          # 没抛错 → 判据失败
    assert dim.judge_raised("TypeError")["ok"] is False   # 抛错但不是预期类型
    assert dim.judge_raised("AttributeError")["ok"] is True


# ── export / 文件格式 ───────────────────────────────────────────────
def _write(path: Path, data: bytes) -> str:
    path.write_bytes(data)
    return str(path)


def test_dwg_judge_pass_and_magic_fail(tmp_path) -> None:
    mem = D("memory", [circle()])
    re = D("reopened", [circle()])
    good = _write(tmp_path / "a.dwg", b"AC1032" + b"\0" * 4096)
    res = export.judge_dwg(rb(D("b", []), mem, re), path=good, since=0)
    assert res["ok"], res
    assert res["detail"]["head"] == "AC1032"

    bad = _write(tmp_path / "b.dwg", b"NOTDWG" + b"\0" * 4096)
    res = export.judge_dwg(rb(D("b", []), mem, re), path=bad, since=0)
    assert res["checks"]["magic"] is False

    res = export.judge_dwg(rb(D("b", []), mem, re),
                           path=str(tmp_path / "missing.dwg"), since=0)
    assert res["checks"]["file"] is False


def test_dwg_judge_detects_stale_file(tmp_path) -> None:
    p = tmp_path / "old.dwg"
    p.write_bytes(b"AC1032" + b"\0" * 4096)
    stale_since = p.stat().st_mtime + 10          # 文件比用例开始还旧
    res = export.judge_dwg(rb(D("b", []), D("m", [circle()]), D("r", [circle()])),
                           path=str(p), since=stale_since)
    assert res["checks"]["file"] is False


def test_dwg_judge_detects_reopen_count_mismatch(tmp_path) -> None:
    p = _write(tmp_path / "c.dwg", b"AC1032" + b"\0" * 4096)
    res = export.judge_dwg(rb(D("b", []), D("m", [circle()]),
                              D("reopened", [])),
                           path=p, since=0)
    assert res["checks"]["counts"] is False


DXF_TEXT = (
    "  0\r\nSECTION\r\n  2\r\nHEADER\r\n  9\r\n$ACADVER\r\n  1\r\nAC1032\r\n"
    "  0\r\nENDSEC\r\n  0\r\nSECTION\r\n  2\r\nENTITIES\r\n"
    "  0\r\nCIRCLE\r\n  8\r\n0\r\n 10\r\n10.0\r\n 20\r\n20.0\r\n 40\r\n25.0\r\n"
    "  0\r\nLINE\r\n  8\r\n0\r\n 10\r\n0.0\r\n 20\r\n0.0\r\n 11\r\n60.0\r\n 21\r\n0.0\r\n"
    "  0\r\nENDSEC\r\n  0\r\nEOF\r\n"
)


def test_dxf_minimal_parser_counts_entities(tmp_path) -> None:
    p = _write(tmp_path / "t.dxf", DXF_TEXT.encode("latin-1"))
    counts = dxfinfo._minimal_sections(open(p, "rb").read())
    assert counts == {"CIRCLE": 1, "LINE": 1}
    fams = dxfinfo.histogram(counts, dxfinfo.family_of_dxftype)
    assert fams == {"CIRCLE": 1, "LINE": 1}


def test_dxf_read_falls_back_without_ezdxf(tmp_path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "ezdxf", None)      # 强制走上 import 失败
    p = _write(tmp_path / "t2.dxf", DXF_TEXT.encode("latin-1"))
    info = dxfinfo.read(p)
    assert info["ok"], info
    assert info["reader"] == "minimal-groupcode"
    assert info["sections"] == ["HEADER", "ENTITIES"]
    assert info["families"] == {"CIRCLE": 1, "LINE": 1}


def test_dxf_read_rejects_non_dxf(tmp_path) -> None:
    p = _write(tmp_path / "x.dxf", b"hello world")
    info = dxfinfo.read(p)
    assert info["ok"] is False and info["why"]


def test_judge_dxf_compares_families(tmp_path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "ezdxf", None)
    p = _write(tmp_path / "t3.dxf", DXF_TEXT.encode("latin-1"))
    dxf = dxfinfo.read(p)
    mem = D("memory", [circle(), E("L1", "LINE", ObjectName="AcDbLine")])
    re = D("dxf-reopened", [circle(), E("L1", "LINE", ObjectName="AcDbLine")])
    res = export.judge_dxf(rb(D("b", []), mem, dxf_reopened=re),
                           path=p, since=0, dxf=dxf)
    assert res["ok"], res
    assert res["detail"]["families_memory"] == {"CIRCLE": 1, "LINE": 1}

    mem_extra = D("memory", [circle(), E("L1", "LINE", ObjectName="AcDbLine"),
                             E("T1", "TEXT", ObjectName="AcDbText")])
    res = export.judge_dxf(rb(D("b", []), mem_extra, dxf_reopened=re),
                           path=p, since=0, dxf=dxf)
    assert res["checks"]["counts"] is False


def make_pdf(path: Path, *, size=(1190.551, 841.890), ops: bool = True,
             pages: int = 1, header: bytes = b"%PDF-1.7") -> str:
    content = b"q 0 0 m 100 100 l S Q\n" if ops else b""
    stream = zlib.compress(content)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    for i in range(pages):
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %f %f] "
                    b"/Contents 3 0 R >>" % (size[0], size[1]))
    body = header + b"\n"
    for i, obj in enumerate(objs, 1):
        body += b"%d 0 obj\n%s\nendobj\n" % (i, obj)
    body += (b"9 0 obj\n<< /Length %d /Filter /FlateDecode >>\nstream\n"
             % len(stream) + stream + b"\nendstream\nendobj\n%%EOF\n")
    path.write_bytes(body)
    return str(path)


def test_pdf_parse_a3_and_ink(tmp_path) -> None:
    p = make_pdf(tmp_path / "a3.pdf")
    info = pdfinfo.parse(p)
    assert info["ok"] and info["pages"] == 1
    assert pdfinfo.size_matches_a3(info["size_pt"])
    assert info["vector_ops"] > 0

    blank = make_pdf(tmp_path / "blank.pdf", ops=False)
    info = pdfinfo.parse(blank)
    assert info["ok"] is False and "空白" in info["why"]


def test_pdf_a4_is_not_a3(tmp_path) -> None:
    p = make_pdf(tmp_path / "a4.pdf", size=(595.276, 841.890))
    info = pdfinfo.parse(p)
    assert info["ok"]
    assert pdfinfo.size_matches_a3(info["size_pt"]) is False


def test_judge_pdf_checks_all_layers(tmp_path) -> None:
    mem = D("memory", [circle()])
    re = D("reopened", [circle()])
    good = make_pdf(tmp_path / "ok.pdf")
    plot = {"ok": True, "device": "DWG To PDF.pc3", "media": "ISO_A3",
            "backgroundplot_restored": True, "elapsed_s": 0.4}
    res = export.judge_pdf(rb(D("b", []), mem, re), path=good, since=0, plot=plot)
    assert res["ok"], res
    assert res["detail"]["size_pt"] == pytest.approx([1190.551, 841.890])

    no_plot = dict(plot, backgroundplot_restored=False)
    res = export.judge_pdf(rb(D("b", []), mem, re), path=good, since=0, plot=no_plot)
    assert res["checks"]["env_restored"] is False

    res = export.judge_pdf(rb(D("b", []), mem, re),
                           path=make_pdf(tmp_path / "a4b.pdf", size=(595.276, 841.89)),
                           since=0, plot=plot)
    assert res["checks"]["size_a3"] is False


# ── block / table ───────────────────────────────────────────────────
BOM_BLOCK = {
    "BOM_MARK": {
        "count": 3,
        "types": {"CIRCLE": 1, "ATTRIBUTEDEFINITION": 2},
        "attdefs": [
            {"TagString": "PART_NO", "TextString": "P-001"},
            {"TagString": "MATERIAL", "TextString": "Q235"},
        ],
    }
}


def _blocks(meta):
    return {"blocks": meta}


def test_block_define_pass_and_fail() -> None:
    good = rb(D("b", [], meta=_blocks({})), D("m", [], meta=_blocks(BOM_BLOCK)),
              D("r", [], meta=_blocks(BOM_BLOCK)))
    res = bt.judge_block_define(good, block_name="BOM_MARK",
                                attdefs={"PART_NO": "P-001", "MATERIAL": "Q235"},
                                entity_types={"CIRCLE": 1, "ATTRIBUTEDEFINITION": 2})
    assert res["ok"], res
    assert res["detail"]["block_types"] == {"CIRCLE": 1, "ATTRIBUTEDEFINITION": 2}

    short = {"BOM_MARK": dict(BOM_BLOCK["BOM_MARK"],
                              attdefs=[{"TagString": "PART_NO", "TextString": "P-001"}],
                              types={"CIRCLE": 1, "ATTRIBUTEDEFINITION": 1})}
    bad = rb(D("b", [], meta=_blocks({})), D("m", [], meta=_blocks(short)),
             D("r", [], meta=_blocks(short)))
    res = bt.judge_block_define(bad, block_name="BOM_MARK",
                                attdefs={"PART_NO": "P-001", "MATERIAL": "Q235"},
                                entity_types={"CIRCLE": 1, "ATTRIBUTEDEFINITION": 2})
    assert res["ok"] is False
    assert res["checks"]["attdef_count"] is False
    assert res["checks"]["attdef_values"] is False


def _ref(attrs, insertion=(100.0, 0.0, 0.0), handle="R1"):
    return E(handle, "BLOCKREFERENCE", ObjectName="AcDbBlockReference",
             Name="BOM_MARK", InsertionPoint=list(insertion), HasAttributes=True,
             attributes=[{"TagString": k, "TextString": v} for k, v in attrs.items()])


def test_block_insert_pass_and_short_attributes_fail() -> None:
    full = _ref({"PART_NO": "P-777", "MATERIAL": "45#"})
    good = rb(D("b", []), D("m", [full]), D("r", [full]))
    res = bt.judge_block_insert(good, block_name="BOM_MARK",
                                attrs={"PART_NO": "P-777", "MATERIAL": "45#"},
                                insertion=(100, 0, 0))
    assert res["ok"], res

    short = _ref({"PART_NO": "P-777"})
    bad = rb(D("b", []), D("m", [short]), D("r", [short]))
    res = bt.judge_block_insert(bad, block_name="BOM_MARK",
                                attrs={"PART_NO": "P-777", "MATERIAL": "45#"},
                                insertion=(100, 0, 0))
    assert res["ok"] is False
    assert res["checks"]["attr_count"] is False
    assert res["checks"]["attr_values"] is False


def test_block_insert_wrong_value_fails() -> None:
    ent = _ref({"PART_NO": "P-777", "MATERIAL": "Q235"})
    res = bt.judge_block_insert(
        rb(D("b", []), D("m", [ent]), D("r", [ent])), block_name="BOM_MARK",
        attrs={"PART_NO": "P-777", "MATERIAL": "45#"}, insertion=(100, 0, 0))
    assert res["ok"] is False and res["checks"]["attr_values"] is False


TABLE_GRID = [["NO.", "NAME", "QTY"], ["1", "BRACKET", "2"],
              ["2", "PLATE", "3"], ["TOTAL", "", "5"]]
TABLE_CELLS = {"0,0": "NO.", "0,1": "NAME", "0,2": "QTY",
               "1,0": "1", "1,1": "BRACKET", "1,2": "2",
               "2,0": "2", "2,1": "PLATE", "2,2": "3",
               "3,0": "TOTAL", "3,2": "5"}


def _table(grid, rows=4, cols=3):
    return E("T1", "ACDBTABLE", ObjectName="AcDbTable", rows=rows, columns=cols,
             cells=grid)


def test_table_pass_and_sum() -> None:
    tbl = _table(TABLE_GRID)
    res = bt.judge_table(rb(D("b", []), D("m", [tbl]), D("r", [tbl])),
                         rows=4, cols=3, cells=TABLE_CELLS, sum_column=2)
    assert res["ok"], res
    assert res["detail"]["sum"]["sum_parts"] == 5.0


def test_table_wrong_total_fails_sum() -> None:
    grid = [row[:] for row in TABLE_GRID]
    grid[3][2] = "6"
    tbl = _table(grid)
    res = bt.judge_table(rb(D("b", []), D("m", [tbl]), D("r", [tbl])),
                         rows=4, cols=3, cells=TABLE_CELLS, sum_column=2)
    assert res["ok"] is False
    assert res["checks"]["sum"] is False


# 真机 BOM 的排法：0 行是合并的标题行，1 行表头，2–3 明细，4 合计
BOM5_GRID = [["BOM", "", ""], ["NO.", "NAME", "QTY"],
             ["1", "BRACKET", "2"], ["2", "PLATE", "3"],
             ["TOTAL", "", "5"]]
BOM5_CELLS = {"0,0": "BOM", "1,0": "NO.", "1,1": "NAME", "1,2": "QTY",
              "2,0": "1", "2,1": "BRACKET", "2,2": "2",
              "3,0": "2", "3,1": "PLATE", "3,2": "3",
              "4,0": "TOTAL", "4,2": "5"}


def test_table_bom_with_title_row() -> None:
    tbl = _table(BOM5_GRID, rows=5, cols=3)
    res = bt.judge_table(rb(D("b", []), D("m", [tbl]), D("r", [tbl])),
                         rows=5, cols=3, cells=BOM5_CELLS, sum_column=2,
                         detail_rows=(2, 3), total_row=4)
    assert res["ok"], res
    assert res["detail"]["sum"]["detail_rows"] == [2, 3]
    assert res["detail"]["sum"]["sum_parts"] == 5.0
    assert res["detail"]["sum"]["total_row"] == 4


def test_table_title_row_cells_lost_on_reopen_fails() -> None:
    """本机真实故障的回归：标题行的第 1..n 列落盘重开后是空的。"""
    tbl = _table(BOM5_GRID, rows=5, cols=3)
    lost = [row[:] for row in BOM5_GRID]
    lost[0] = ["BOM", "", ""]           # 标题行其余列本来就没写
    reopened = _table(lost, rows=5, cols=3)
    res = bt.judge_table(rb(D("b", []), D("m", [tbl]), D("r", [reopened])),
                         rows=5, cols=3, cells=BOM5_CELLS, sum_column=2,
                         detail_rows=(2, 3), total_row=4)
    # 只写 (0,0) 的排法是能过 L4 的；这里验证换个写法就会失败
    assert res["checks"]["reopen"] is True
    lost2 = [row[:] for row in BOM5_GRID]
    lost2[0] = ["BOM", "X", "Y"]
    res2 = bt.judge_table(rb(D("b", []), D("m", [_table(lost2, 5, 3)]),
                             D("r", [_table(lost, 5, 3)])),
                          rows=5, cols=3, cells=BOM5_CELLS, sum_column=2,
                          detail_rows=(2, 3), total_row=4)
    assert res2["checks"]["reopen"] is False


def test_table_cells_lost_on_reopen_fails() -> None:
    """本机实测的真实故障：中文单元格落盘重开后变空串。"""
    tbl = _table(TABLE_GRID)
    lost = [row[:] for row in TABLE_GRID]
    lost[0] = ["NO.", "", ""]
    reopened = _table(lost)
    res = bt.judge_table(rb(D("b", []), D("m", [tbl]), D("r", [reopened])),
                         rows=4, cols=3, cells=TABLE_CELLS, sum_column=2)
    assert res["ok"] is False
    assert res["checks"]["reopen"] is False
    assert res["detail"]["reopen"]["mismatch"]["cells"]


# ── 能力表与 registry 对得上 ────────────────────────────────────────
def test_caps_cover_families() -> None:
    from acadkit import caps

    for fam in ("geom", "text", "dim", "gdt", "symbol", "table", "block",
                "frame", "layer", "env", "solid", "boolean", "export",
                "view", "lisp"):
        assert caps.FAMILIES.get(fam), "族 %s 没有能力" % fam


def test_cap_ids_exist_in_registry_yaml() -> None:
    from acadkit import caps

    known = {c["id"] for c in registry.load()["capabilities"]}
    extra = {c.id for c in caps.CAPS} - known - {"dim.api_missing",
                                                 "block.short_attributes"}
    assert not extra, "能力指向了 registry 里不存在的 id：%r" % sorted(extra)


def test_negative_controls_declared() -> None:
    from acadkit import caps

    neg = {c.id for c in caps.CAPS if c.is_negative or c.expect == "fail"}
    assert neg == {"dim.api_missing", "block.short_attributes"}


def test_cap_params_and_cases_are_consistent() -> None:
    from acadkit import caps

    ids = [c.id for c in caps.CAPS]
    assert len(ids) == len(set(ids)), "能力 id 有重复"
    # 参数必须可 JSON 序列化（CLI/MCP 都要传）
    for cap in caps.CAPS:
        json.dumps(cap.params, default=str)
        case = cap.case({"__probe__": 1})
        assert case.id == cap.id
        assert callable(case.build) and callable(case.judge)
