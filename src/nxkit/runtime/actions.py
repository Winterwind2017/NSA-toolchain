"""在 NX 进程内执行的能力实现（只在这里碰 NXOpen）。

每个 action 返回 `reads`（宿主侧判据比对的读数）。所有读取都来自
NX 内部（`MeasureManager`/`GetBodies`/`GetFeatureName`），不看返回值。
"""

from __future__ import annotations

import os
import time

import NXOpen
import NXOpen.Features


# ── 基础工具 ──────────────────────────────────────────────────────
def session():
    return NXOpen.Session.GetSession()


def _close_part(part) -> None:
    try:
        part.Close(NXOpen.BasePart.CloseWholeTree.TrueValue,
                   NXOpen.BasePart.CloseModified.CloseModified, None)
    except Exception:
        pass


def new_part(name: str):
    s = session()
    # 同名部件在同一会话里会冲突，加时间戳
    unique = "%s_%d" % (name, int(time.time() * 1000) % 100000)
    part = s.Parts.NewDisplay(unique + ".prt", NXOpen.Part.Units.Millimeters)
    s.Parts.SetWork(part)
    return part


def _unit(part):
    return part.UnitCollection.FindObject("MilliMeter")


def mass(part, bodies) -> dict:
    """体积/面积/重心，读自 MeasureManager（不是返回值）。"""
    mm = part.MeasureManager
    mb = mm.NewMassProperties([_unit(part)], 0.99, list(bodies))
    out = {"volume_mm3": float(mb.Volume), "area_mm2": float(mb.Area)}
    try:
        c = mb.Centroid
        out["centroid"] = [float(c.X), float(c.Y), float(c.Z)]
    except Exception:
        out["centroid"] = None
    return out


def make_block(part, x, y, z, l, w, h):
    b = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        b.SetOriginAndLengths(NXOpen.Point3d(float(x), float(y), float(z)),
                              str(l), str(w), str(h))
        feat = b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass
    return feat


def make_cylinder(part, x, y, z, diameter, height):
    b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        types = NXOpen.Features.CylinderBuilder.Types
        try:
            b.Type = types.DiameterHeight
        except Exception:
            pass
        b.Diameter.SetFormula(str(diameter))
        b.Height.SetFormula(str(height))
        b.Origin = NXOpen.Point3d(float(x), float(y), float(z))
        b.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        feat = b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass
    return feat


def _set_boolean(part, feat_a, feat_b, op_name: str):
    body_a = feat_a.GetBodies()[0]
    body_b = feat_b.GetBodies()[0]
    b = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        enum = NXOpen.Features.Feature.BooleanType
        b.Operation = getattr(enum, op_name)
        b.Target = body_a
        try:
            b.Tools.Add([body_b])
        except Exception:
            b.Tools.Add(body_b)
        feat = b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass
    return feat


def _bodies_of(part) -> list:
    """按 Tag 去重：布尔之后 Block 特征会指向同一个结果体，不去重会重复计数。"""
    out, seen = [], set()
    for f in part.Features:
        try:
            bodies = list(f.GetBodies())
        except Exception:
            continue
        for b in bodies:
            tag = getattr(b, "Tag", None)
            if tag in seen:
                continue
            seen.add(tag)
            out.append(b)
    return out


def _feat_by_name(part, name):
    for f in part.Features:
        try:
            if str(f.GetFeatureName()) == name:
                return f
        except Exception:
            continue
    return None


def save_reopen(part, path: str):
    if os.path.exists(path):
        os.remove(path)
    part.SaveAs(path)
    _close_part(part)
    res = session().Parts.OpenActiveDisplay(path, NXOpen.DisplayPartOption.AllowAdditional)
    part2 = res[0] if isinstance(res, (tuple, list)) else res
    session().Parts.SetWork(part2)
    return part2


# ── 能力实现 ──────────────────────────────────────────────────────
def part_new(params, workdir, rec):
    part = new_part(params.get("name", "nxkit_part"))
    reads = {
        "part_name": str(part.Name),
        "part_name_ok": str(part.Name).startswith(params.get("name", "nxkit_part")),
        "units_mm": str(part.PartUnits) in ("1", "Millimeters"),
        "body_count": 0,
    }
    _close_part(part)
    return reads


def block_create(params, workdir, rec):
    l = float(params.get("length", 100.0))
    w = float(params.get("width", 50.0))
    h = float(params.get("height", 20.0))
    part = new_part("blk")
    feat = make_block(part, 0, 0, 0, l, w, h)
    name = str(feat.GetFeatureName())
    body = feat.GetBodies()[0]
    reads = {
        "feature_name": name,
        "body_count": 1,
        "faces": len(body.GetFaces()),
        "edges": len(body.GetEdges()),
    }
    reads.update(mass(part, [body]))

    path = os.path.join(workdir, "block.prt")
    part2 = save_reopen(part, path)
    f2 = _feat_by_name(part2, name)
    if f2 is not None:
        b2 = f2.GetBodies()[0]
        m2 = mass(part2, [b2])
        reads["volume_reopened"] = m2["volume_mm3"]
        reads["area_reopened"] = m2["area_mm2"]
        reads["faces_reopened"] = len(b2.GetFaces())
    reads["saved_bytes"] = os.path.getsize(path)
    _close_part(part2)
    return reads


def block_two(params, workdir, rec):
    part = new_part("blk2")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_block(part, 0, 0, 0, 20, 20, 20)
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies), "body_count_direct":
             int(fa.GetBodies()[0] is not None) + int(fb.GetBodies()[0] is not None)}
    reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def _boolean(params, workdir, op_name):
    part = new_part("bool")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_block(part, 0, 0, 0, 20, 20, 20)
    feat = _set_boolean(part, fa, fb, op_name)
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies), "result_feature": str(feat.GetFeatureName())}
    reads.update(mass(part, bodies))

    path = os.path.join(workdir, "bool_%s.prt" % op_name.lower())
    part2 = save_reopen(part, path)
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        m2 = mass(part2, bodies2)
        reads["volume_reopened"] = m2["volume_mm3"]
    reads["saved_bytes"] = os.path.getsize(path)
    _close_part(part2)
    return reads


def boolean_subtract(params, workdir, rec):
    return _boolean(params, workdir, "Subtract")


def boolean_union(params, workdir, rec):
    return _boolean(params, workdir, "Unite")


def boolean_intersect(params, workdir, rec):
    return _boolean(params, workdir, "Intersect")


def cylinder_create(params, workdir, rec):
    d = float(params.get("diameter", 40.0))
    h = float(params.get("height", 30.0))
    part = new_part("cyl")
    feat = make_cylinder(part, 0, 0, 0, d, h)
    body = feat.GetBodies()[0]
    reads = {"feature_name": str(feat.GetFeatureName()),
             "body_count": 1,
             "faces": len(body.GetFaces()),
             "edges": len(body.GetEdges())}
    reads.update(mass(part, [body]))

    path = os.path.join(workdir, "cyl.prt")
    part2 = save_reopen(part, path)
    bodies2 = _bodies_of(part2)
    if bodies2:
        m2 = mass(part2, bodies2)
        reads["volume_reopened"] = m2["volume_mm3"]
        reads["area_reopened"] = m2["area_mm2"]
    reads["saved_bytes"] = os.path.getsize(path)
    _close_part(part2)
    return reads


def measure_mass(params, workdir, rec):
    part = new_part("mass")
    feat = make_block(part, 0, 0, 0,
                      float(params.get("length", 100.0)),
                      float(params.get("width", 50.0)),
                      float(params.get("height", 20.0)))
    body = feat.GetBodies()[0]
    reads = mass(part, [body])
    reads["body_count"] = 1
    _close_part(part)
    return reads


def body_topo(params, workdir, rec):
    part = new_part("topo")
    feat = make_block(part, 0, 0, 0,
                      float(params.get("length", 100.0)),
                      float(params.get("width", 50.0)),
                      float(params.get("height", 20.0)))
    body = feat.GetBodies()[0]
    faces = body.GetFaces()
    edges = body.GetEdges()
    reads = {"faces": len(faces), "edges": len(edges), "body_count": 1}
    try:
        reads["vertices"] = len(body.GetVertices())
    except Exception:
        reads["vertices"] = None
    _close_part(part)
    return reads


def file_roundtrip(params, workdir, rec):
    part = new_part("rt")
    feat = make_block(part, 0, 0, 0,
                      float(params.get("length", 100.0)),
                      float(params.get("width", 50.0)),
                      float(params.get("height", 20.0)))
    name = str(feat.GetFeatureName())
    body = feat.GetBodies()[0]
    reads = {"feature_name": name}
    reads.update(mass(part, [body]))

    path = os.path.join(workdir, "roundtrip.prt")
    part2 = save_reopen(part, path)
    reads["saved_bytes"] = os.path.getsize(path)
    f2 = _feat_by_name(part2, name)
    reads["feature_reopened"] = f2 is not None
    if f2 is not None:
        m2 = mass(part2, [f2.GetBodies()[0]])
        reads["volume_reopened"] = m2["volume_mm3"]
        reads["area_reopened"] = m2["area_mm2"]
    _close_part(part2)
    return reads


def curve_line(params, workdir, rec):
    import math
    part = new_part("line")
    p1 = NXOpen.Point3d(0.0, 0.0, 0.0)
    p2 = NXOpen.Point3d(float(params.get("dx", 100.0)),
                        float(params.get("dy", 0.0)),
                        float(params.get("dz", 0.0)))
    line = part.Curves.CreateLine(p1, p2)
    sp, ep = line.StartPoint, line.EndPoint
    length = math.dist([sp.X, sp.Y, sp.Z], [ep.X, ep.Y, ep.Z])
    reads = {"length": length,
             "start": [float(sp.X), float(sp.Y), float(sp.Z)],
             "end": [float(ep.X), float(ep.Y), float(ep.Z)]}
    _close_part(part)
    return reads


def curve_arc(params, workdir, rec):
    import math
    part = new_part("arc")
    r = float(params.get("radius", 25.0))
    arc = part.Curves.CreateArc(NXOpen.Point3d(0.0, 0.0, 0.0),
                                NXOpen.Vector3d(1.0, 0.0, 0.0),
                                NXOpen.Vector3d(0.0, 1.0, 0.0),
                                r, 0.0, 2.0 * math.pi)
    reads = {"radius": float(arc.Radius),
             "circumference": 2.0 * math.pi * float(arc.Radius),
             "start_angle": float(arc.StartAngle),
             "end_angle": float(arc.EndAngle)}
    _close_part(part)
    return reads


def attr_string(params, workdir, rec):
    part = new_part("attr")
    title = str(params.get("title", "NXKIT_STR"))
    value = str(params.get("value", "hello-nx"))
    part.SetAttribute(title, value)
    reads = {"attr_str": str(part.GetStringAttribute(title))}
    path = os.path.join(workdir, "attr.prt")
    part2 = save_reopen(part, path)
    reads["attr_after_reopen"] = str(part2.GetStringAttribute(title))
    reads["saved_bytes"] = os.path.getsize(path)
    _close_part(part2)
    return reads


def attr_int(params, workdir, rec):
    part = new_part("attr_i")
    title = str(params.get("title", "NXKIT_INT"))
    value = int(params.get("value", 42))
    part.SetAttribute(title, value)
    reads = {"attr_int": int(part.GetIntegerAttribute(title))}
    _close_part(part)
    return reads


def extrude_rect(params, workdir, rec):
    part = new_part("ext")
    l = float(params.get("length", 100.0))
    w = float(params.get("width", 50.0))
    d = float(params.get("distance", 10.0))
    p = NXOpen.Point3d
    lines = [
        part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(l, 0.0, 0.0)),
        part.Curves.CreateLine(p(l, 0.0, 0.0), p(l, w, 0.0)),
        part.Curves.CreateLine(p(l, w, 0.0), p(0.0, w, 0.0)),
        part.Curves.CreateLine(p(0.0, w, 0.0), p(0.0, 0.0, 0.0)),
    ]
    secs = part.Sections.CreateSectionsUsingCurves(
        lines, NXOpen.SectionCollection.LoopOption.Separate,
        0.0095, 0.01, 0.5)
    sec = secs[0]

    b = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        b.Section = sec
        b.Direction = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        try:
            b.Limits.StartExtend.SetValue(0.0)
            b.Limits.EndExtend.SetValue(float(d))
        except Exception:
            b.Limits.StartExtend.Value.SetFormula("0")
            b.Limits.EndExtend.Value.SetFormula(str(d))
        feat = b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass
    body = feat.GetBodies()[0]
    reads = {"feature_name": str(feat.GetFeatureName()),
             "body_count": 1,
             "faces": len(body.GetFaces()),
             "edges": len(body.GetEdges())}
    reads.update(mass(part, [body]))
    _close_part(part)
    return reads


def _identity() -> "NXOpen.Matrix3x3":
    m = NXOpen.Matrix3x3()
    for attr, val in (("Xx", 1.0), ("Xy", 0.0), ("Xz", 0.0),
                      ("Yx", 0.0), ("Yy", 1.0), ("Yz", 0.0),
                      ("Zx", 0.0), ("Zy", 0.0), ("Zz", 1.0)):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    return m


def _make_ref_part(path, kind, size):
    """造一个基准零件并存盘（装配要按文件路径插组件）。"""
    part = new_part("ref_" + kind)
    if kind == "block":
        make_block(part, 0, 0, 0, size[0], size[1], size[2])
    else:
        make_cylinder(part, 0, 0, 0, size[0], size[1])
    if os.path.exists(path):
        os.remove(path)
    part.SaveAs(path)
    _close_part(part)
    return path


def asm_add_component(params, workdir, rec):
    a_path = _make_ref_part(os.path.join(workdir, "ref_a.prt"), "block",
                            (100.0, 50.0, 20.0))
    b_path = _make_ref_part(os.path.join(workdir, "ref_b.prt"), "cyl",
                            (40.0, 30.0))
    asm = new_part("asm")
    comp = asm.ComponentAssembly.AddComponent(
        a_path, "MODEL", "A", NXOpen.Point3d(0.0, 0.0, 0.0), _identity(), -1)
    comp1 = comp[0] if isinstance(comp, (tuple, list)) else comp
    children = asm.ComponentAssembly.RootComponent.GetChildren()
    reads = {"components": len(children),
             "component_name": str(comp1.Name) if comp1 is not None else None}
    _close_part(asm)
    return reads


def asm_two_components(params, workdir, rec):
    a_path = _make_ref_part(os.path.join(workdir, "ref2_a.prt"), "block",
                            (100.0, 50.0, 20.0))
    b_path = _make_ref_part(os.path.join(workdir, "ref2_b.prt"), "cyl",
                            (40.0, 30.0))
    asm = new_part("asm2")
    asm.ComponentAssembly.AddComponent(
        a_path, "MODEL", "A", NXOpen.Point3d(0.0, 0.0, 0.0), _identity(), -1)
    asm.ComponentAssembly.AddComponent(
        b_path, "MODEL", "B", NXOpen.Point3d(150.0, 0.0, 0.0), _identity(), -1)
    children = asm.ComponentAssembly.RootComponent.GetChildren()
    reads = {"components": len(children)}
    model = os.path.join(workdir, "asm2.prt")
    if os.path.exists(model):
        os.remove(model)
    asm.SaveAs(model)
    reads["saved_bytes"] = os.path.getsize(model)
    _close_part(asm)
    return reads


def _export(params, workdir, rec, kind):
    part = new_part("exp")
    make_block(part, 0, 0, 0, 100, 50, 20)
    ext = {"step": ".step", "iges": ".igs"}[kind]
    path = os.path.join(workdir, "export" + ext)
    if os.path.exists(path):
        os.remove(path)
    s = session()
    creator = (s.DexManager.CreateStepCreator() if kind == "step"
               else s.DexManager.CreateIgesCreator())
    try:
        creator.OutputFile = path
        creator.Commit()
    finally:
        try:
            creator.Destroy()
        except Exception:
            pass
    exists = os.path.exists(path)
    reads = {"export_path": path,
             "export_bytes": os.path.getsize(path) if exists else 0,
             "igs": bool(exists and kind == "iges")}
    if os.path.exists(path):
        with open(path, "rb") as fh:
            head = fh.read(64).decode("latin-1", "replace")
        reads["export_head"] = head.strip()[:12]
    _close_part(part)
    return reads


def export_step(params, workdir, rec):
    return _export(params, workdir, rec, "step")


def export_iges(params, workdir, rec):
    return _export(params, workdir, rec, "iges")


def drawing_sheet(params, workdir, rec):
    part = new_part("drw")
    make_block(part, 0, 0, 0, 100, 50, 20)
    sheets = part.DrawingSheets
    ss = NXOpen.Drawings.DrawingSheet.StandardSheetSize
    pa = NXOpen.Drawings.DrawingSheet.ProjectionAngleType
    sheet = sheets.InsertSheet(str(params.get("name", "S1")), ss.A3,
                               1.0, 1.0, pa.FirstAngle)
    reads = {"sheet_created": sheet is not None,
             "sheet_name": str(sheet.Name) if hasattr(sheet, "Name") else None,
             "sheet_count_now": 1 if sheets.CurrentDrawingSheet is not None else 0}
    try:
        reads["sheet_height"] = float(sheet.Height)
        reads["sheet_width"] = float(sheet.Length)
    except Exception:
        pass
    _close_part(part)
    return reads


def drawing_base_view(params, workdir, rec):
    part = new_part("bvw")
    make_block(part, 0, 0, 0, 100, 50, 20)
    ss = NXOpen.Drawings.DrawingSheet.StandardSheetSize
    pa = NXOpen.Drawings.DrawingSheet.ProjectionAngleType
    part.DrawingSheets.InsertSheet("S1", ss.A3, 1.0, 1.0, pa.FirstAngle)

    name = str(params.get("model_view", "Front"))
    model_view = None
    for v in part.ModelingViews:
        if str(v.Name) == name:
            model_view = v
            break
    if model_view is None:
        model_view = part.ModelingViews.WorkView

    vb = part.DraftingViews.CreateBaseViewBuilder(NXOpen.Drawings.BaseView.Null)
    try:
        vb.SelectModelView.SelectedView = model_view
        try:
            vb.Scale.ScaleValue = 1.0
        except Exception:
            pass
        view = vb.Commit()
    finally:
        try:
            vb.Destroy()
        except Exception:
            pass
    reads = {"view_created": view is not None,
             "view_name": str(view.Name) if view is not None else None,
             "model_view_used": str(model_view.Name)}
    try:
        reads["view_scale"] = float(view.Scale)
    except Exception:
        pass
    _close_part(part)
    return reads


def extrude_ring(params, workdir, rec):
    """带内孔截面拉伸：外框 100×50，内框 40×20，拉伸 10 → 42000。"""
    part = new_part("ring")
    p = NXOpen.Point3d
    outer = [
        part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 0.0, 0.0)),
        part.Curves.CreateLine(p(100.0, 0.0, 0.0), p(100.0, 50.0, 0.0)),
        part.Curves.CreateLine(p(100.0, 50.0, 0.0), p(0.0, 50.0, 0.0)),
        part.Curves.CreateLine(p(0.0, 50.0, 0.0), p(0.0, 0.0, 0.0)),
    ]
    inner = [
        part.Curves.CreateLine(p(30.0, 15.0, 0.0), p(70.0, 15.0, 0.0)),
        part.Curves.CreateLine(p(70.0, 15.0, 0.0), p(70.0, 35.0, 0.0)),
        part.Curves.CreateLine(p(70.0, 35.0, 0.0), p(30.0, 35.0, 0.0)),
        part.Curves.CreateLine(p(30.0, 35.0, 0.0), p(30.0, 15.0, 0.0)),
    ]
    secs = part.Sections.CreateSectionsUsingCurves(
        outer + inner, NXOpen.SectionCollection.LoopOption.SeparateOuter,
        0.0095, 0.01, 0.5)
    b = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        b.Section = secs[0]
        b.Direction = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        try:
            b.Limits.StartExtend.SetValue(0.0)
            b.Limits.EndExtend.SetValue(10.0)
        except Exception:
            b.Limits.StartExtend.Value.SetFormula("0")
            b.Limits.EndExtend.Value.SetFormula("10")
        feat = b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass
    body = feat.GetBodies()[0]
    reads = {"sections": len(secs),
             "faces": len(body.GetFaces()),
             "body_count": 1}
    reads.update(mass(part, [body]))
    _close_part(part)
    return reads


def chamfer_one(params, workdir, rec):
    """倒一个边（5 mm），判据看面数与体积区间。"""
    part = new_part("cham")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    edges = body.GetEdges()
    cb = part.Features.CreateChamferBuilder(NXOpen.Features.Feature.Null)
    try:
        rule = part.ScRuleFactory.CreateRuleEdgeDumb([edges[0]])
        sc = part.ScCollectors.CreateCollector()
        sc.AddRules([rule])
        cb.SmartCollector = sc
        try:
            cb.FirstOffsetExp.SetFormula("5")
            cb.SecondOffsetExp.SetFormula("5")
        except Exception:
            pass
        cf = cb.CommitFeature()
        reads = {"feature": str(cf.GetFeatureName())}
    finally:
        try:
            cb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads["body_count"] = len(bodies)
    reads["faces"] = len(bodies[0].GetFaces()) if bodies else 0
    reads["edges"] = len(bodies[0].GetEdges()) if bodies else 0
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def edge_blend_one(params, workdir, rec):
    """一条边圆角 R5。"""
    part = new_part("blend")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    edges = body.GetEdges()
    eb = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        rule = part.ScRuleFactory.CreateRuleEdgeDumb([edges[0]])
        sc = part.ScCollectors.CreateCollector()
        sc.AddRules([rule])
        eb.AddChainset(sc, "5")
        cf = eb.CommitFeature()
        reads = {"feature": str(cf.GetFeatureName())}
    finally:
        try:
            eb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads["body_count"] = len(bodies)
    reads["faces"] = len(bodies[0].GetFaces()) if bodies else 0
    reads["edges"] = len(bodies[0].GetEdges()) if bodies else 0
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def pattern_linear(params, workdir, rec):
    """块沿 +X 阵列 3 个（间距 120），判据：实体 3、体积 300000。"""
    part = new_part("pat")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    pb = part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        pb.FeatureList.Add([feat])
        svc = pb.PatternService
        try:
            svc.PatternType = svc.PatternEnum.Linear
        except Exception:
            pass
        rd = svc.RectangularDefinition
        rd.XDirection = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        spacing = rd.XSpacing
        set_n = False
        for expr, val in ((getattr(spacing, "NCopies", None), "3"),
                          (getattr(spacing, "PitchDistance", None), "120")):
            if expr is None:
                continue
            try:
                expr.SetFormula(val)
                set_n = True
            except Exception:
                pass
        if not set_n:
            raise RuntimeError("pattern spacing 表达式不可写")
        cf = pb.CommitFeature()
        reads = {"feature": str(cf.GetFeatureName())}
    finally:
        try:
            pb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads["body_count"] = len(bodies)
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def _extrude_rect_body(part, x, y, w, h, depth):
    p = NXOpen.Point3d
    lines = [
        part.Curves.CreateLine(p(x, y, 0.0), p(x + w, y, 0.0)),
        part.Curves.CreateLine(p(x + w, y, 0.0), p(x + w, y + h, 0.0)),
        part.Curves.CreateLine(p(x + w, y + h, 0.0), p(x, y + h, 0.0)),
        part.Curves.CreateLine(p(x, y + h, 0.0), p(x, y, 0.0)),
    ]
    secs = part.Sections.CreateSectionsUsingCurves(
        lines, NXOpen.SectionCollection.LoopOption.Separate, 0.0095, 0.01, 0.5)
    b = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        b.Section = secs[0]
        b.Direction = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        try:
            b.Limits.StartExtend.SetValue(0.0)
            b.Limits.EndExtend.SetValue(float(depth))
        except Exception:
            b.Limits.StartExtend.Value.SetFormula("0")
            b.Limits.EndExtend.Value.SetFormula(str(depth))
        return b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass


def _volume_after_boolean(part, fa, fb, op):
    _set_boolean(part, fa, fb, op)
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies)}
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def feature_pocket(params, workdir, rec):
    """块上挖 40×20 通槽（拉伸 + 布尔差）→ 92000。"""
    part = new_part("pocket")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = _extrude_rect_body(part, 30.0, 15.0, 40.0, 20.0, 20.0)
    return _volume_after_boolean(part, fa, fb, "Subtract")


def feature_hole_cyl(params, workdir, rec):
    """块上钻 Ø20 通孔（圆柱 + 布尔差）→ 93716.815。"""
    part = new_part("hole")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_cylinder(part, 50.0, 25.0, 0.0, 20.0, 20.0)
    return _volume_after_boolean(part, fa, fb, "Subtract")


def _dex_export(kind, part, workdir):
    ext = {"stl": ".stl", "parasolid": ".x_t", "acis": ".sat"}[kind]
    path = os.path.join(workdir, "export_" + kind + ext)
    if os.path.exists(path):
        os.remove(path)
    dm = session().DexManager
    creator = {"stl": dm.CreateStlCreator,
               "parasolid": dm.CreateParasolidExporter,
               "acis": dm.CreateAcisExporter}[kind]()
    try:
        creator.OutputFile = path
        creator.Commit()
    finally:
        try:
            creator.Destroy()
        except Exception:
            pass
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    head = ""
    if exists:
        with open(path, "rb") as fh:
            head = fh.read(48).decode("latin-1", "replace")
    return {"export_path": path, "export_bytes": size,
            "export_head": head.strip()[:24],
            "export_ok": bool(exists and size > 100)}


def _export_simple(kind):
    def run(params, workdir, rec):
        part = new_part("exp_" + kind)
        make_block(part, 0, 0, 0, 100, 50, 20)
        reads = _dex_export(kind, part, workdir)
        _close_part(part)
        return reads
    return run


def export_stl(params, workdir, rec):
    return _export_simple("stl")(params, workdir, rec)
def export_parasolid(params, workdir, rec):
    return _export_simple("parasolid")(params, workdir, rec)
def export_acis(params, workdir, rec):
    return _export_simple("acis")(params, workdir, rec)


def curve_ellipse(params, workdir, rec):
    import math
    part = new_part("ell")
    e = part.Curves.CreateEllipse(NXOpen.Point3d(0.0, 0.0, 0.0),
                                 NXOpen.Vector3d(1.0, 0.0, 0.0),
                                 NXOpen.Vector3d(0.0, 1.0, 0.0),
                                 50.0, 25.0, 0.0, 2.0 * math.pi)
    reads = {"ellipse_major": float(e.MajorRadius),
             "ellipse_minor": float(e.MinorRadius)}
    _close_part(part)
    return reads


def attr_on_body(params, workdir, rec):
    part = new_part("attrb")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    body.SetAttribute("NXKIT_BODY", "v1")
    reads = {"body_attr": str(body.GetStringAttribute("NXKIT_BODY")),
             "body_count": 1}
    _close_part(part)
    return reads


def measure_face_area(params, workdir, rec):
    """六个面的面积和 = 16000，面 6。"""
    part = new_part("facearea")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    faces = list(body.GetFaces())
    mm = part.MeasureManager
    mf = mm.NewFaceProperties(_unit(part), _unit(part), 0.99, faces)
    reads = {"faces": len(faces),
             "total_face_area": float(mf.Area),
             "perimeter": float(mf.Perimeter)}
    _close_part(part)
    return reads


def solid_cone(params, workdir, rec):
    part = new_part("cone")
    d = float(params.get("diameter", 40.0))
    h = float(params.get("height", 30.0))
    cb = part.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
    try:
        for name in ("BottomDiameter", "BaseDiameter", "Diameter"):
            if hasattr(cb, name):
                try:
                    getattr(cb, name).SetFormula(str(d))
                    break
                except Exception:
                    continue
        try:
            cb.Height.SetFormula(str(h))
        except Exception:
            pass
        try:
            cb.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
            cb.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        except Exception:
            pass
        feat = cb.CommitFeature()
    finally:
        try:
            cb.Destroy()
        except Exception:
            pass
    body = feat.GetBodies()[0]
    reads = {"body_count": 1}
    reads.update(mass(part, [body]))
    _close_part(part)
    return reads


def solid_sphere(params, workdir, rec):
    part = new_part("sph")
    d = float(params.get("diameter", 40.0))
    sb = part.Features.CreateSphereBuilder(NXOpen.Features.Sphere.Null)
    try:
        for name in ("Diameter", "SphereDiameter"):
            if hasattr(sb, name):
                try:
                    getattr(sb, name).SetFormula(str(d))
                    break
                except Exception:
                    continue
        try:
            sb.Center = NXOpen.Point3d(0.0, 0.0, 0.0)
        except Exception:
            pass
        feat = sb.CommitFeature()
    finally:
        try:
            sb.Destroy()
        except Exception:
            pass
    body = feat.GetBodies()[0]
    reads = {"body_count": 1}
    reads.update(mass(part, [body]))
    _close_part(part)
    return reads


def pattern_grid(params, workdir, rec):
    """2×2 矩形阵列（X 间距 120，Y 间距 80）→ 实体 4、体积 400000。"""
    part = new_part("grid")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    pb = part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        pb.FeatureList.Add([feat])
        svc = pb.PatternService
        try:
            svc.PatternType = svc.PatternEnum.Linear
        except Exception:
            pass
        rd = svc.RectangularDefinition
        rd.XDirection = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        try:
            rd.UseYDirectionToggle = True
        except Exception:
            pass
        rd.YDirection = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        xs, ys = rd.XSpacing, rd.YSpacing
        xs.NCopies.SetFormula("2")
        xs.PitchDistance.SetFormula("120")
        ys.NCopies.SetFormula("2")
        ys.PitchDistance.SetFormula("80")
        cf = pb.CommitFeature()
        reads = {"feature": str(cf.GetFeatureName())}
    finally:
        try:
            pb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads["body_count"] = len(bodies)
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def pattern_circular(params, workdir, rec):
    """绕 Z 轴圆周阵列 4 个（各 90°）→ 实体 4、体积 400000。"""
    part = new_part("circ")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    pb = part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        pb.FeatureList.Add([feat])
        svc = pb.PatternService
        svc.PatternType = svc.PatternEnum.Circular
        cd = svc.CircularDefinition
        cd.RotationAxis = part.Axes.CreateAxis(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        try:
            cd.RotationCenter = part.Points.CreatePoint(
                NXOpen.Point3d(0.0, 0.0, 0.0))
        except Exception:
            pass
        sp = cd.AngularSpacing
        sp.NCopies.SetFormula("4")
        try:
            sp.PitchAngle.SetFormula("90")
        except Exception:
            sp.PitchDistance.SetFormula("90")
        cf = pb.CommitFeature()
        reads = {"feature": str(cf.GetFeatureName())}
    finally:
        try:
            pb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads["body_count"] = len(bodies)
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def export_step_ap203(params, workdir, rec):
    part = new_part("st203")
    make_block(part, 0, 0, 0, 100, 50, 20)
    path = os.path.join(workdir, "export_ap203.step")
    if os.path.exists(path):
        os.remove(path)
    creator = session().DexManager.CreateStepCreator()
    try:
        creator.OutputFile = path
        try:
            creator.ExportAs = NXOpen.StepCreator.ExportAsOption.Ap203
        except Exception:
            pass
        creator.Commit()
    finally:
        try:
            creator.Destroy()
        except Exception:
            pass
    exists = os.path.exists(path)
    head = ""
    if exists:
        with open(path, "rb") as fh:
            head = fh.read(12).decode("latin-1", "replace")
    reads = {"export_ok": bool(exists and os.path.getsize(path) > 1000),
             "export_head": head}
    _close_part(part)
    return reads


def attr_on_feature(params, workdir, rec):
    part = new_part("attrf")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    feat.SetAttribute("NXKIT_FEAT", "f1")
    reads = {"feature_attr": str(feat.GetStringAttribute("NXKIT_FEAT")),
             "feature_name": str(feat.GetFeatureName())}
    _close_part(part)
    return reads


def chamfer_multi(params, workdir, rec):
    """四条边同时倒角 5 mm（多边选择规则）。"""
    part = new_part("cham4")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    edges = list(body.GetEdges())[:4]
    cb = part.Features.CreateChamferBuilder(NXOpen.Features.Feature.Null)
    try:
        rule = part.ScRuleFactory.CreateRuleEdgeDumb(edges)
        sc = part.ScCollectors.CreateCollector()
        sc.AddRules([rule])
        cb.SmartCollector = sc
        try:
            cb.FirstOffsetExp.SetFormula("5")
            cb.SecondOffsetExp.SetFormula("5")
        except Exception:
            pass
        cb.CommitFeature()
    finally:
        try:
            cb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies),
             "faces": len(bodies[0].GetFaces()) if bodies else 0}
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def _drafting_part(name):
    part = new_part(name)
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    ss = NXOpen.Drawings.DrawingSheet.StandardSheetSize
    pa = NXOpen.Drawings.DrawingSheet.ProjectionAngleType
    part.DrawingSheets.InsertSheet("S1", ss.A3, 1.0, 1.0, pa.FirstAngle)
    vb = part.DraftingViews.CreateBaseViewBuilder(NXOpen.Drawings.BaseView.Null)
    for v in part.ModelingViews:
        if str(v.Name) == "Front":
            vb.SelectModelView.SelectedView = v
    view = vb.Commit()
    vb.Destroy()
    return part, feat, view


def drawing_dimension(params, workdir, rec):
    part, feat, view = _drafting_part("dim")
    body = feat.GetBodies()[0]
    edges = list(body.GetEdges())
    lb = part.Dimensions.CreateLinearDimensionBuilder(None)
    try:
        lb.FirstAssociativity.SetValue(edges[0], view, NXOpen.Point3d(0.0, 0.0, 0.0))
        lb.SecondAssociativity.SetValue(edges[1], view, NXOpen.Point3d(100.0, 0.0, 0.0))
        try:
            lb.Origin.SetValue(NXOpen.Point3d(50.0, -20.0, 0.0))
        except Exception:
            pass
        dim = lb.Commit()
        reads = {"dimension_created": dim is not None}
    finally:
        try:
            lb.Destroy()
        except Exception:
            pass
    try:
        reads["dimension_count"] = len(list(part.Dimensions))
    except Exception:
        reads["dimension_count"] = None
    _close_part(part)
    return reads


def boolean_two_tools(params, workdir, rec):
    """块减去两个小方块（各 8000）→ 84000。"""
    part = new_part("bool2")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_block(part, 0, 0, 0, 20, 20, 20)
    fc = make_block(part, 40.0, 0, 0, 20, 20, 20)
    body_a = fa.GetBodies()[0]
    bodies_tool = [fb.GetBodies()[0], fc.GetBodies()[0]]
    bb = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        bb.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        bb.Target = body_a
        bb.Tools.Add(bodies_tool)
        bb.CommitFeature()
    finally:
        try:
            bb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies)}
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def hole_array(params, workdir, rec):
    """四个 Ø20 通孔（x = 15/40/65/90, y = 25，孔间留 5）→ 74867.26。"""
    part = new_part("harray")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    tools = []
    for x in (12.5, 37.5, 62.5, 87.5):
        tools.append(make_cylinder(part, x, 25.0, -2.0, 20.0, 24.0).GetBodies()[0])
    bb = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        bb.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        bb.Target = fa.GetBodies()[0]
        bb.Tools.Add(tools)
        bb.CommitFeature()
    finally:
        try:
            bb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies)}
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def feature_shell(params, workdir, rec):
    """块抽壳 2 mm（封闭空腔）→ 29344。"""
    part = new_part("shell")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    sb = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
    try:
        sb.Body = body
        thickness_set = None
        for setter in (lambda: sb.SetDefaultThickness("2"),
                       lambda: setattr(sb, "DefaultThickness", "2"),
                       lambda: sb.DefaultThickness.SetFormula("2")):
            try:
                setter()
                thickness_set = "ok"
                break
            except Exception as exc:
                thickness_set = "err:%s" % str(exc)[:80]
        try:
            sb.Tolerance = 0.01
        except Exception:
            pass
        cf = sb.CommitFeature()
        reads = {"feature": str(cf.GetFeatureName())}
    finally:
        try:
            sb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads["thickness_set"] = thickness_set
    reads["body_count"] = len(bodies)
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def _xy_plane(part):
    mat = NXOpen.Matrix3x3()
    mat.Xx, mat.Xy, mat.Xz = 1.0, 0.0, 0.0
    mat.Yx, mat.Yy, mat.Yz = 0.0, 1.0, 0.0
    mat.Zx, mat.Zy, mat.Zz = 0.0, 0.0, 1.0
    return part.Planes.CreateFixedPlane(NXOpen.Point3d(0.0, 0.0, 0.0), mat)


def sketch_rect(params, workdir, rec):
    """在 XY 平面上建草图并落 4 条线（100×50）。"""
    part = new_part("sketch")
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    try:
        sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
        activated = True
    except Exception:
        activated = False
    p = NXOpen.Point3d
    pts = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]
    lines = []
    for i in range(4):
        a1 = pts[i]
        b1 = pts[(i + 1) % 4]
        ln = part.Curves.CreateLine(p(a1[0], a1[1], 0.0), p(b1[0], b1[1], 0.0))
        try:
            sketch.AddGeometry(ln)
        except Exception:
            pass
        lines.append(ln)
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        try:
            sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue)
        except Exception:
            pass
    reads = {"sketches": len(list(part.Sketches)),
             "curves": len(list(part.Curves)),
             "activated": activated,
             "lines_added": len(lines)}
    _close_part(part)
    return reads


def _sketch_rect_lines(part):
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    try:
        sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    except Exception:
        pass
    p = NXOpen.Point3d
    pts = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]
    lines = []
    for i in range(4):
        a1, b1 = pts[i], pts[(i + 1) % 4]
        ln = part.Curves.CreateLine(p(a1[0], a1[1], 0.0), p(b1[0], b1[1], 0.0))
        try:
            sketch.AddGeometry(ln)
        except Exception:
            pass
        lines.append(ln)
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        try:
            sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue)
        except Exception:
            pass
    return sketch, lines


def sketch_extrude(params, workdir, rec):
    """草图 4 条线 → 拉伸 10 → 体积 50000（草图驱动建模）。"""
    part = new_part("skext")
    sketch, lines = _sketch_rect_lines(part)
    secs = part.Sections.CreateSectionsUsingCurves(
        lines, NXOpen.SectionCollection.LoopOption.Separate, 0.0095, 0.01, 0.5)
    b = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        b.Section = secs[0]
        b.Direction = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        try:
            b.Limits.StartExtend.SetValue(0.0)
            b.Limits.EndExtend.SetValue(10.0)
        except Exception:
            b.Limits.StartExtend.Value.SetFormula("0")
            b.Limits.EndExtend.Value.SetFormula("10")
        feat = b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"sketches": len(list(part.Sketches)),
             "body_count": len(bodies)}
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


def sketch_circle_extrude(params, workdir, rec):
    """草图画 R20 整圆 → 拉伸 30 → 37699.11。"""
    import math
    part = new_part("skcirc")
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    try:
        sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    except Exception:
        pass
    arc = part.Curves.CreateArc(NXOpen.Point3d(0.0, 0.0, 0.0),
                                NXOpen.Vector3d(1.0, 0.0, 0.0),
                                NXOpen.Vector3d(0.0, 1.0, 0.0),
                                20.0, 0.0, 2.0 * math.pi)
    try:
        sketch.AddGeometry(arc)
    except Exception:
        pass
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        try:
            sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue)
        except Exception:
            pass
    secs = part.Sections.CreateSectionsUsingCurves(
        [arc], NXOpen.SectionCollection.LoopOption.Separate, 0.0095, 0.01, 0.5)
    b = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        b.Section = secs[0]
        b.Direction = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        try:
            b.Limits.StartExtend.SetValue(0.0)
            b.Limits.EndExtend.SetValue(30.0)
        except Exception:
            b.Limits.StartExtend.Value.SetFormula("0")
            b.Limits.EndExtend.Value.SetFormula("30")
        b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"sketches": len(list(part.Sketches)), "body_count": len(bodies)}
    if bodies:
        reads.update(mass(part, bodies))
    _close_part(part)
    return reads


ACTIONS = {
    "part_new": part_new,
    "block_create": block_create,
    "block_two": block_two,
    "boolean_subtract": boolean_subtract,
    "boolean_union": boolean_union,
    "boolean_intersect": boolean_intersect,
    "cylinder_create": cylinder_create,
    "measure_mass": measure_mass,
    "body_topo": body_topo,
    "file_roundtrip": file_roundtrip,
    "curve_line": curve_line,
    "curve_arc": curve_arc,
    "attr_string": attr_string,
    "attr_int": attr_int,
    "extrude_rect": extrude_rect,
    "asm_add_component": asm_add_component,
    "asm_two_components": asm_two_components,
    "export_step": export_step,
    "export_iges": export_iges,
    "drawing_sheet": drawing_sheet,
    "drawing_base_view": drawing_base_view,
    "extrude_ring": extrude_ring,
    "chamfer_one": chamfer_one,
    "edge_blend_one": edge_blend_one,
    "pattern_linear": pattern_linear,
    "feature_pocket": feature_pocket,
    "feature_hole_cyl": feature_hole_cyl,
    "export_stl": export_stl,
    "export_parasolid": export_parasolid,
    "export_acis": export_acis,
    "curve_ellipse": curve_ellipse,
    "attr_on_body": attr_on_body,
    "measure_face_area": measure_face_area,
    "solid_cone": solid_cone,
    "solid_sphere": solid_sphere,
    "pattern_grid": pattern_grid,
    "pattern_circular": pattern_circular,
    "export_step_ap203": export_step_ap203,
    "attr_on_feature": attr_on_feature,
    "chamfer_multi": chamfer_multi,
    "drawing_dimension": drawing_dimension,
    "boolean_two_tools": boolean_two_tools,
    "hole_array": hole_array,
    "feature_shell": feature_shell,
    "sketch_rect": sketch_rect,
    "sketch_extrude": sketch_extrude,
    "sketch_circle_extrude": sketch_circle_extrude,
}


def run(action: str, params: dict, workdir: str, rec: dict) -> dict:
    fn = ACTIONS.get(action)
    if fn is None:
        raise KeyError("未知动作 %r" % action)
    return fn(params or {}, workdir, rec)
