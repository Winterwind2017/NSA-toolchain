"""这一轮新增能力的离线判据测试（不需要 AutoCAD / AeData）。

覆盖：CSG 投影、三视图判据、Electrical 读取判据、PLC 模块图判据、P&ID 符号判据、
PDF 逐页解析。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acadkit import csg                                    # noqa: E402
from acadkit.build.projection import (LAYER_AXIS, LAYER_HIDDEN,  # noqa: E402
                                      LAYER_VISIBLE, MODEL)
from acadkit.judges import ae as j_ae                      # noqa: E402
from acadkit.judges import pid as j_pid                    # noqa: E402
from acadkit.judges import pdfinfo                         # noqa: E402
from acadkit.judges import projection as j_proj            # noqa: E402
from acadkit.judges.base import Drawing, Entity, Readback  # noqa: E402


def E(handle, type_name, **attrs):
    return Entity(handle=handle, type=type_name, attrs=dict(attrs))


def D(source, entities):
    return Drawing(source=source, insunits=4, entities=list(entities), meta={})


def RB(before, memory, reopened=None):
    return Readback(before=before, memory=memory, reopened=reopened)


# ── CSG 投影 ──────────────────────────────────────────────────────
def test_csg_projection_counts_are_deterministic() -> None:
    front = csg.project(MODEL, "front")
    top = csg.project(MODEL, "top")
    left = csg.project(MODEL, "left")
    assert len(front) == 11 and len(top) == 6 and len(left) == 11
    assert sum(1 for p in front if p["hidden"]) == 3
    assert sum(1 for p in top if p["kind"] == "circle") == 2


def test_csg_bbox_and_footprint() -> None:
    bb = csg.bbox({"type": "box", "x": [0, 100], "y": [0, 60], "z": [0, 20]})
    assert bb == (0.0, 100.0, 0.0, 60.0, 0.0, 20.0)
    fp = csg.footprint(bb, "front")
    assert fp[:4] == (0.0, 100.0, 0.0, 20.0)


def test_csg_subtract_hole_lines_are_hidden() -> None:
    # 孔轴沿 X（与主视的 u 轴同向）→ 主视里是两条隐藏线
    model = [{"type": "box", "x": [0, 100], "y": [0, 60], "z": [0, 20]},
             {"type": "cyl", "axis": "x", "c": [30, 10], "a": [0, 100], "r": 5,
              "op": "sub"}]
    front = csg.project(model, "front")
    holes = [p for p in front if p.get("src") == "hole"]
    assert len(holes) == 2 and all(p["hidden"] and p["kind"] == "seg"
                                   for p in holes)


def test_csg_hole_along_depth_projects_as_circle() -> None:
    # 孔轴沿 Y = 主视的深度轴 → 主视里是圆
    model = [{"type": "box", "x": [0, 100], "y": [0, 60], "z": [0, 20]},
             {"type": "cyl", "axis": "y", "c": [50, 10], "a": [0, 60], "r": 5,
              "op": "sub"}]
    front = csg.project(model, "front")
    circles = [p for p in front
               if p["kind"] == "circle" and p.get("src") == "hole"]
    assert len(circles) == 1 and circles[0]["r"] == 5


# ── 三视图判据 ────────────────────────────────────────────────────
def _projection_entities() -> list:
    ents = []
    for view in ("front", "top", "left"):
        for p in csg.project(MODEL, view):
            if p["kind"] == "circle":
                ents.append(E("C%d" % len(ents), "CIRCLE",
                              Layer=LAYER_HIDDEN if p.get("hidden") else LAYER_VISIBLE))
            else:
                lay = (LAYER_AXIS if p.get("src") == "axis"
                       else LAYER_HIDDEN if p.get("hidden") else LAYER_VISIBLE)
                ents.append(E("L%d" % len(ents), "LINE", Layer=lay))
    return ents


def _recorded() -> dict:
    return {"model": MODEL,
            "sizes": {"front": [100.0, 30.0], "top": [100.0, 60.0],
                      "left": [60.0, 30.0]},
            "hidden_linetype": "HIDDEN", "views": {}}


def test_projection_judge_passes_and_fails() -> None:
    ents = _projection_entities()
    ok = j_proj.judge_projection(RB(D("b", []), D("m", ents), D("r", ents)),
                                 recorded=_recorded())
    assert ok["ok"] is True
    bad = j_proj.judge_projection(RB(D("b", []), D("m", ents[:-1])),
                                  recorded=_recorded())
    assert bad["ok"] is False
    assert bad["checks"]["visible_count"] is False or bad["checks"]["hidden_count"] is False


# ── Electrical 读取 ───────────────────────────────────────────────
def _ae_record() -> dict:
    return {"ok": True, "aedata": "C:/AeData",
            "catalogs": ["wd_lang1.mdb"], "db": "wd_lang1.mdb",
            "tables": ["MATRIX"], "sample_table": "MATRIX",
            "row_count": 120, "sample": {"ID": "3", "ENU (English-US)": "Emergency Stop"},
            "hash_before": "a" * 64, "hash_after": "a" * 64, "unchanged": True,
            "error": None}


def test_ae_judge_requires_unchanged_file() -> None:
    ok = j_ae.judge_ae_db(_ae_record())
    assert ok["ok"] is True
    bad = j_ae.judge_ae_db({**_ae_record(), "unchanged": False})
    assert bad["ok"] is False and bad["checks"]["readonly"] is False
    empty = j_ae.judge_ae_db({"aedata": None, "error": "no AeData"})
    assert empty["ok"] is False and empty["checks"]["aedata"] is False


# ── PLC 模块图 ────────────────────────────────────────────────────
def _plc_entities(n: int = 8) -> list:
    ents = [E("P0", "LWPOLYLINE", Layer="0")]
    ents.append(E("T0", "TEXT", TextString="1SBP 26 0023 R 1001"))
    ents.append(E("T1", "TEXT", TextString="8 DISCRETE IN"))
    for i in range(n):
        ents.append(E("L%d" % i, "LINE"))
        ents.append(E("C%d" % i, "CIRCLE"))
        ents.append(E("T%d" % (i + 2), "TEXT", TextString="I0.%d" % i))
    return ents


def test_plc_judge_counts_and_code() -> None:
    rec = {"ok": True, "CODE": "1SBP 26 0023 R 1001", "DESCRIPTION": "8 DISCRETE IN",
           "drawn": {"points": 8, "lines": 8, "circles": 8, "texts": 10,
                     "polyline": 1}}
    ok = j_ae.judge_plc(RB(D("b", []), D("m", _plc_entities())), recorded=rec)
    assert ok["ok"] is True
    bad = j_ae.judge_plc(RB(D("b", []), D("m", _plc_entities(7))), recorded=rec)
    assert bad["ok"] is False


# ── P&ID 符号 ─────────────────────────────────────────────────────
def _pid_entities() -> list:
    ents = [E("L%d" % i, "LINE") for i in range(14)]
    ents += [E("C0", "CIRCLE"), E("C1", "CIRCLE")]
    for i, t in enumerate(("HV-01", "P-01", "PI-01")):
        ents.append(E("T%d" % i, "TEXT", TextString=t))
    return ents


def test_pid_judge_requires_all_tags() -> None:
    rec = {"lines": 14, "circles": 2, "texts": ["HV-01", "P-01", "PI-01"]}
    ok = j_pid.judge_pid(RB(D("b", []), D("m", _pid_entities())), recorded=rec)
    assert ok["ok"] is True
    broken = [e for e in _pid_entities()
              if not (e.type == "TEXT" and e.attrs.get("TextString") == "P-01")]
    bad = j_pid.judge_pid(RB(D("b", []), D("m", broken)), recorded=rec)
    assert bad["ok"] is False and bad["checks"]["tags"] is False


# ── PDF 逐页解析 ──────────────────────────────────────────────────
def _tiny_pdf(pages: int) -> bytes:
    body: list = [b""]                       # 占位：对象 1 = Pages
    page_nums = []
    for _ in range(pages):
        content = "0 0 m 100 100 l S"
        body.append(b"<< /Length %d >>\nstream\n%s\nendstream"
                    % (len(content), content.encode()))
        content_num = len(body)
        body.append(b"<< /Type /Page /Parent 1 0 R /MediaBox [0 0 1190.551 841.89]"
                    b" /Contents %d 0 R >>" % content_num)
        page_nums.append(len(body))
    kids = b" ".join(b"%d 0 R" % n for n in page_nums)
    body[0] = b"<< /Type /Pages /Count %d /Kids [%s] >>" % (pages, kids)
    out = bytearray(b"%PDF-1.7\n")
    offs = [0]
    for i, o in enumerate(body, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(body) + 1)
    for off in offs[1:]:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(body) + 1, len(body) + 1, xref))
    return bytes(out)


def test_pdf_pages_detail(tmp_path: Path) -> None:
    p = tmp_path / "two.pdf"
    p.write_bytes(_tiny_pdf(2))
    info = pdfinfo.parse(str(p))
    assert info["pages"] == 2
    assert len(info["pages_detail"]) == 2
    assert all(d["size_pt"] == [1190.551, 841.89] for d in info["pages_detail"])
    assert all(d["vector_ops"] > 0 for d in info["pages_detail"])
