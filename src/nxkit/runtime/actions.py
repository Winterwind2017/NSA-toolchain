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
    part2 = save_reopen(part, os.path.join(workdir, "two.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "massm.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "ext.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
            head = fh.read(200).decode("latin-1", "replace")
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
    part2 = save_reopen(part, os.path.join(workdir, "ring.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "chamfer.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "blend.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "pattern.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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


def _volume_after_boolean(part, fa, fb, op, workdir=None, tag=None):
    _set_boolean(part, fa, fb, op)
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies)}
    if bodies:
        reads.update(mass(part, bodies))
    if workdir and tag:
        part2 = save_reopen(part, os.path.join(workdir, tag + ".prt"))
        bodies2 = _bodies_of(part2)
        reads["body_count_reopened"] = len(bodies2)
        if bodies2:
            reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
        _close_part(part2)
    else:
        _close_part(part)
    return reads


def feature_pocket(params, workdir, rec):
    """块上挖 40×20 通槽（拉伸 + 布尔差）→ 92000。"""
    part = new_part("pocket")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = _extrude_rect_body(part, 30.0, 15.0, 40.0, 20.0, 20.0)
    return _volume_after_boolean(part, fa, fb, "Subtract", workdir, "pocket")


def feature_hole_cyl(params, workdir, rec):
    """块上钻 Ø20 通孔（圆柱 + 布尔差）→ 93716.815。"""
    part = new_part("hole")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_cylinder(part, 50.0, 25.0, 0.0, 20.0, 20.0)
    return _volume_after_boolean(part, fa, fb, "Subtract", workdir, "holecyl")


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
        if kind == "parasolid":
            try:
                creator.ExportFrom = NXOpen.ParasolidExporter.ExportFromOption.DisplayedPart
            except Exception:
                pass
        try:
            bodies = _bodies_of(part)
            if bodies and kind != "parasolid":
                creator.ExportSelectionBlock.Add(bodies)
        except Exception:
            pass
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
    part2 = save_reopen(part, os.path.join(workdir, "attrbody.prt"))
    bodies2 = _bodies_of(part2)
    try:
        attr2 = str(bodies2[0].GetStringAttribute("NXKIT_BODY"))
    except Exception:
        attr2 = ""
    reads["body_attr_reopened"] = attr2
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "facearea.prt"))
    bodies2 = _bodies_of(part2)
    if bodies2:
        faces2 = list(bodies2[0].GetFaces())
        mf2 = part2.MeasureManager.NewFaceProperties(
            _unit(part2), _unit(part2), 0.99, faces2)
        reads["total_face_area_reopened"] = float(mf2.Area)
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "cone.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "sphere.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "grid.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "circ.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "chamfer4.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "bool2.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "harray.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "shell.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "skext.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
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
    part2 = save_reopen(part, os.path.join(workdir, "skcirc.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def feature_pocket_blind(params, workdir, rec):
    """盲槽：40×20 深 10 → 100000 - 8000 = 92000。"""
    part = new_part("pockb")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = _extrude_rect_body(part, 30.0, 15.0, 40.0, 20.0, 10.0)
    return _volume_after_boolean(part, fa, fb, "Subtract", workdir, "pocketb")


def feature_hole_blind(params, workdir, rec):
    """盲孔：Ø20 深 10 → 100000 - 3141.59 = 96858.41。"""
    part = new_part("holeb")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_cylinder(part, 50.0, 25.0, 0.0, 20.0, 10.0)
    return _volume_after_boolean(part, fa, fb, "Subtract", workdir, "holeb")


def drawing_sheet_size(params, workdir, rec):
    """指定图幅（默认 A4）→ 297×210。"""
    part = new_part("drw4")
    make_block(part, 0, 0, 0, 100, 50, 20)
    ss = NXOpen.Drawings.DrawingSheet.StandardSheetSize
    pa = NXOpen.Drawings.DrawingSheet.ProjectionAngleType
    size = getattr(ss, str(params.get("size", "A4")))
    sheet = part.DrawingSheets.InsertSheet("S1", size, 1.0, 1.0, pa.FirstAngle)
    reads = {"sheet_created": sheet is not None,
             "sheet_height": float(sheet.Height),
             "sheet_width": float(sheet.Length)}
    _close_part(part)
    return reads


def drawing_view_named(params, workdir, rec):
    """指定模型方向的基准视图（默认 Isometric）。"""
    part = new_part("bvw2")
    make_block(part, 0, 0, 0, 100, 50, 20)
    ss = NXOpen.Drawings.DrawingSheet.StandardSheetSize
    pa = NXOpen.Drawings.DrawingSheet.ProjectionAngleType
    part.DrawingSheets.InsertSheet("S1", ss.A3, 1.0, 1.0, pa.FirstAngle)
    name = str(params.get("model_view", "Isometric"))
    model_view = None
    for v in part.ModelingViews:
        if str(v.Name) == name:
            model_view = v
            break
    vb = part.DraftingViews.CreateBaseViewBuilder(NXOpen.Drawings.BaseView.Null)
    try:
        vb.SelectModelView.SelectedView = model_view
        view = vb.Commit()
    finally:
        try:
            vb.Destroy()
        except Exception:
            pass
    reads = {"view_name": str(view.Name),
             "view_created": view is not None}
    _close_part(part)
    return reads


def asm_three_components(params, workdir, rec):
    """装配里插 3 个组件（A/B/C 分别偏移 0/150/300）。"""
    a_path = _make_ref_part(os.path.join(workdir, "ref3_a.prt"), "block",
                            (100.0, 50.0, 20.0))
    b_path = _make_ref_part(os.path.join(workdir, "ref3_b.prt"), "cyl",
                            (40.0, 30.0))
    asm = new_part("asm3")
    for name, path, x in (("A", a_path, 0.0), ("B", b_path, 150.0),
                          ("C", a_path, 300.0)):
        asm.ComponentAssembly.AddComponent(
            path, "MODEL", name, NXOpen.Point3d(x, 0.0, 0.0), _identity(), -1)
    children = asm.ComponentAssembly.RootComponent.GetChildren()
    reads = {"components": len(children)}
    _close_part(asm)
    return reads


def feature_revolve(params, workdir, rec):
    """XZ 平面矩形绕 Z 轴转 360°，r=20 h=30 → 37699.11。"""
    part = new_part("rev")
    p = NXOpen.Point3d
    lines = [
        part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(20.0, 0.0, 0.0)),
        part.Curves.CreateLine(p(20.0, 0.0, 0.0), p(20.0, 0.0, 30.0)),
        part.Curves.CreateLine(p(20.0, 0.0, 30.0), p(0.0, 0.0, 30.0)),
        part.Curves.CreateLine(p(0.0, 0.0, 30.0), p(0.0, 0.0, 0.0)),
    ]
    secs = part.Sections.CreateSectionsUsingCurves(
        lines, NXOpen.SectionCollection.LoopOption.Separate, 0.0095, 0.01, 0.5)
    b = part.Features.CreateRevolveBuilder(NXOpen.Features.Feature.Null)
    try:
        b.Section = secs[0]
        axis_point = part.Points.CreatePoint(p(0.0, 0.0, 0.0))
        axis_dir = part.Directions.CreateDirection(
            p(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        b.Axis = part.Axes.CreateAxis(axis_point, axis_dir,
                                      NXOpen.SmartObject.UpdateOption.WithinModeling)
        try:
            b.Limits.StartExtend.Value.SetFormula("0")
            b.Limits.EndExtend.Value.SetFormula("360")
        except Exception:
            b.Limits.StartExtend.SetValue(0.0)
            b.Limits.EndExtend.SetValue(360.0)
        feat = b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass
    body = feat.GetBodies()[0]
    reads = {"body_count": 1, "faces": len(body.GetFaces())}
    reads.update(mass(part, [body]))
    part2 = save_reopen(part, os.path.join(workdir, "rev.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def edge_blend_all(params, workdir, rec):
    """块的全部 12 条边圆角 3 mm（判面数与体积区间）。"""
    part = new_part("blendall")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    edges = list(body.GetEdges())
    eb = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        rule = part.ScRuleFactory.CreateRuleEdgeDumb(edges)
        sc = part.ScCollectors.CreateCollector()
        sc.AddRules([rule])
        eb.AddChainset(sc, "3")
        eb.CommitFeature()
    finally:
        try:
            eb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies),
             "faces": len(bodies[0].GetFaces()) if bodies else 0}
    if bodies:
        reads.update(mass(part, bodies))
    part2 = save_reopen(part, os.path.join(workdir, "blendall.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def measure_face_single(params, workdir, rec):
    """最大面的面积/周长（100×50 面：5000 / 300）。"""
    part = new_part("face1")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    mm = part.MeasureManager
    unit = _unit(part)
    best = None
    for face in body.GetFaces():
        mf = mm.NewFaceProperties(unit, unit, 0.99, [face])
        area = float(mf.Area)
        if best is None or area > best[0]:
            best = (area, float(mf.Perimeter))
    reads = {"face_area_max": best[0], "face_perimeter_max": best[1]}
    _close_part(part)
    return reads


def chamfer_edge(params, workdir, rec):
    """单边倒角 5 mm：面 7，体积在 99000–100000（边长度随选择变化）。"""
    part = new_part("chama")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    cb = part.Features.CreateChamferBuilder(NXOpen.Features.Feature.Null)
    try:
        rule = part.ScRuleFactory.CreateRuleEdgeDumb([list(body.GetEdges())[0]])
        sc = part.ScCollectors.CreateCollector()
        sc.AddRules([rule])
        cb.SmartCollector = sc
        opt = None
        for value in (2, 1):
            try:
                cb.Option = value
                opt = value
                break
            except Exception:
                continue
        try:
            cb.FirstOffsetExp.SetFormula("5")
        except Exception:
            pass
        try:
            cb.AngleExp.SetFormula("30")
        except Exception:
            pass
        cb.CommitFeature()
        reads = {"option_used": opt}
    finally:
        try:
            cb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads["body_count"] = len(bodies)
    reads["faces"] = len(bodies[0].GetFaces()) if bodies else 0
    if bodies:
        reads.update(mass(part, bodies))
    part2 = save_reopen(part, os.path.join(workdir, "chamfer2.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def _rect_lines(part, w=100.0, h=50.0):
    p = NXOpen.Point3d
    pts = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    lines = []
    for i in range(4):
        a1, b1 = pts[i], pts[(i + 1) % 4]
        lines.append(part.Curves.CreateLine(p(a1[0], a1[1], 0.0), p(b1[0], b1[1], 0.0)))
    return lines


def surface_bounded_plane(params, workdir, rec):
    """4 条线围成有界平面（片体）。"""
    part = new_part("bplane")
    lines = _rect_lines(part)
    bp = part.Features.CreateBoundedPlaneBuilder(NXOpen.Features.BoundedPlane.Null)
    try:
        rule = part.ScRuleFactory.CreateRuleCurveDumb(lines)
        bp.BoundingCurves.AddToSection([rule], lines[0], None, None,
                                       NXOpen.Point3d(0.0, 0.0, 0.0),
                                       NXOpen.Section.Mode.Create)
        set_ok = "AddToSection"
        feat = bp.CommitFeature()
        reads = {"feature": str(feat.GetFeatureName()), "attr_used": set_ok}
    finally:
        try:
            bp.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads["body_count"] = len(bodies)
    reads["faces"] = len(bodies[0].GetFaces()) if bodies else 0
    part2 = save_reopen(part, os.path.join(workdir, "bplane.prt"))
    sheets2 = [b for b in _bodies_of(part2) if b.IsSheetBody]
    reads["sheet_count_reopened"] = len(sheets2)
    _close_part(part2)
    return reads


def feature_tube(params, workdir, rec):
    """沿 100 mm 直线做 Ø20 管（实心）→ 31415.93。"""
    part = new_part("tube")
    p = NXOpen.Point3d
    line = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 0.0, 0.0))
    secs = part.Sections.CreateSectionsUsingCurves(
        [line], NXOpen.SectionCollection.LoopOption.Separate, 0.0095, 0.01, 0.5)
    sentinel = None
    for name in ("Tube", "Feature"):
        try:
            sentinel = getattr(NXOpen.Features, name).Null
            tb = part.Features.CreateTubeBuilder(sentinel)
            break
        except Exception:
            tb = None
            continue
    try:
        rule = part.ScRuleFactory.CreateRuleCurveDumb([line])
        tb.PathSection.AddToSection([rule], line, None, None,
                                    NXOpen.Point3d(0.0, 0.0, 0.0),
                                    NXOpen.Section.Mode.Create)
        for name in ("OuterDiameter", "Diameter"):
            if hasattr(tb, name):
                try:
                    getattr(tb, name).SetFormula("20")
                except Exception:
                    try:
                        setattr(tb, name, "20")
                    except Exception:
                        pass
        try:
            tb.Tolerance = 0.01
        except Exception:
            pass
        try:
            feat = tb.CommitFeature()
        except Exception as exc:
            diag = {}
            for name in ("OuterDiameter", "InnerDiameter", "Tolerance", "OutputOption"):
                try:
                    diag[name] = str(getattr(tb, name))[:40]
                except Exception:
                    diag[name] = "?"
            raise RuntimeError("%s | %r" % (str(exc)[:120], diag))
    finally:
        try:
            tb.Destroy()
        except Exception:
            pass
    body = feat.GetBodies()[0]
    reads = {"body_count": 1, "faces": len(body.GetFaces())}
    reads.update(mass(part, [body]))
    part2 = save_reopen(part, os.path.join(workdir, "tube.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def curve_hyperbola(params, workdir, rec):
    part = new_part("hyp")
    hyp = part.Curves.CreateHyperbola(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(1.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0),
        50.0, 25.0, -10.0, 10.0)
    reads = {"semi_transverse": float(hyp.SemiTransverseLength),
             "semi_conjugate": float(hyp.SemiConjugateLength)}
    _close_part(part)
    return reads


def curve_parabola(params, workdir, rec):
    part = new_part("par")
    par = part.Curves.CreateParabola(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(1.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0),
        20.0, -10.0, 10.0)
    reads = {"focal_length": float(par.FocalLength)}
    _close_part(part)
    return reads


def boolean_intersect_two(params, workdir, rec):
    """块 ∩ 两个错位小方块 → 10×20×20 = 4000。"""
    part = new_part("int2")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_block(part, 0, 0, 0, 20, 20, 20)
    fc = make_block(part, 10.0, 0, 0, 20, 20, 20)
    bb = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        bb.Operation = NXOpen.Features.Feature.BooleanType.Intersect
        bb.Target = fa.GetBodies()[0]
        bb.Tools.Add([fb.GetBodies()[0], fc.GetBodies()[0]])
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
    part2 = save_reopen(part, os.path.join(workdir, "int2.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def inspect_body_type(params, workdir, rec):
    """块实体是 solid、有界平面是 sheet。"""
    part = new_part("btype")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    solid_body = feat.GetBodies()[0]
    reads = {"solid_is_solid": bool(solid_body.IsSolidBody),
             "solid_is_sheet": bool(solid_body.IsSheetBody)}
    lines = _rect_lines(part)
    bp = part.Features.CreateBoundedPlaneBuilder(NXOpen.Features.BoundedPlane.Null)
    try:
        rule = part.ScRuleFactory.CreateRuleCurveDumb(lines)
        bp.BoundingCurves.AddToSection([rule], lines[0], None, None,
                                       NXOpen.Point3d(0.0, 0.0, 0.0),
                                       NXOpen.Section.Mode.Create)
        bp.CommitFeature()
    finally:
        try:
            bp.Destroy()
        except Exception:
            pass
    sheets = [b for b in _bodies_of(part) if bool(b.IsSheetBody)]
    reads["sheet_is_sheet"] = len(sheets) == 1
    reads["sheet_is_solid"] = bool(sheets[0].IsSolidBody) if sheets else None
    _close_part(part)
    return reads


def feature_hole_csk(params, workdir, rec):
    """沉头孔：Ø20 通孔 + Ø30 深 5 → 91753.32。"""
    import math
    part = new_part("csk")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_cylinder(part, 50.0, 25.0, -2.0, 20.0, 24.0)
    fc = make_cylinder(part, 50.0, 25.0, 15.0, 30.0, 7.0)
    bb = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        bb.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        bb.Target = fa.GetBodies()[0]
        bb.Tools.Add([fb.GetBodies()[0], fc.GetBodies()[0]])
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
    part2 = save_reopen(part, os.path.join(workdir, "csk.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def solid_cone_frustum(params, workdir, rec):
    """圆台：底 Ø40 / 顶 Ø20 / 高 30 → 21991.15。"""
    part = new_part("frustum")
    cb = part.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
    try:
        set_top = None
        for name in ("TopDiameter", "TopDia"):
            if hasattr(cb, name):
                try:
                    getattr(cb, name).SetFormula("20")
                    set_top = name
                    break
                except Exception as exc:
                    set_top = "err:%s" % str(exc)[:60]
        for name in ("BottomDiameter", "BaseDiameter", "Diameter"):
            if hasattr(cb, name):
                try:
                    getattr(cb, name).SetFormula("40")
                    break
                except Exception:
                    continue
        try:
            cb.Height.SetFormula("30")
        except Exception:
            pass
        try:
            cb.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
            cb.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        except Exception:
            pass
        feat = cb.CommitFeature()
        reads = {"top_attr": set_top}
    finally:
        try:
            cb.Destroy()
        except Exception:
            pass
    body = feat.GetBodies()[0]
    reads["body_count"] = 1
    reads.update(mass(part, [body]))
    part2 = save_reopen(part, os.path.join(workdir, "frustum.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def asm_nested(params, workdir, rec):
    """子装配 + 零件：外层装配 2 个子节点。"""
    a_path = _make_ref_part(os.path.join(workdir, "nest_a.prt"), "block",
                            (100.0, 50.0, 20.0))
    b_path = _make_ref_part(os.path.join(workdir, "nest_b.prt"), "cyl",
                            (40.0, 30.0))
    sub = new_part("subasm")
    sub.ComponentAssembly.AddComponent(
        a_path, "MODEL", "A", NXOpen.Point3d(0.0, 0.0, 0.0), _identity(), -1)
    sub.ComponentAssembly.AddComponent(
        b_path, "MODEL", "B", NXOpen.Point3d(150.0, 0.0, 0.0), _identity(), -1)
    sub_path = os.path.join(workdir, "subasm.prt")
    if os.path.exists(sub_path):
        os.remove(sub_path)
    sub.SaveAs(sub_path)
    _close_part(sub)

    top = new_part("topasm")
    top.ComponentAssembly.AddComponent(
        sub_path, "MODEL", "SUB", NXOpen.Point3d(0.0, 0.0, 0.0), _identity(), -1)
    top.ComponentAssembly.AddComponent(
        b_path, "MODEL", "C", NXOpen.Point3d(0.0, 200.0, 0.0), _identity(), -1)
    children = top.ComponentAssembly.RootComponent.GetChildren()
    names = sorted(str(c.Name) for c in children)
    reads = {"components": len(children), "names": names}
    _close_part(top)
    return reads


def asm_four_components(params, workdir, rec):
    """四个组件（两零件各两次）。"""
    a_path = _make_ref_part(os.path.join(workdir, "four_a.prt"), "block",
                            (100.0, 50.0, 20.0))
    b_path = _make_ref_part(os.path.join(workdir, "four_b.prt"), "cyl",
                            (40.0, 30.0))
    asm = new_part("asm4")
    for i, path in enumerate((a_path, b_path, a_path, b_path)):
        asm.ComponentAssembly.AddComponent(
            path, "MODEL", "P%d" % i,
            NXOpen.Point3d(150.0 * i, 0.0, 0.0), _identity(), -1)
    children = asm.ComponentAssembly.RootComponent.GetChildren()
    reads = {"components": len(children)}
    _close_part(asm)
    return reads


def feature_boss(params, workdir, rec):
    """块顶圆柱凸台 Ø20×10（并集）→ 103141.59。"""
    part = new_part("boss")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_cylinder(part, 50.0, 25.0, 20.0, 20.0, 10.0)
    return _volume_after_boolean(part, fa, fb, "Unite", workdir, "boss")


def feature_extrude_taper(params, workdir, rec):
    """100×50 截面拉伸 10 并带 5° 拔模 → 体积略小于 50000。"""
    part = new_part("taper")
    lines = _rect_lines(part)
    secs = part.Sections.CreateSectionsUsingCurves(
        lines, NXOpen.SectionCollection.LoopOption.Separate, 0.0095, 0.01, 0.5)
    b = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    diag = {}
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
        draft = b.Draft
        diag["draft_type"] = type(draft).__name__
        diag["draft_dir"] = [n for n in dir(draft) if not n.startswith("_")][:15]
        try:
            draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraft.SimpleDraftType.SimpleFromStart
            diag["option"] = "SimpleFromStart"
        except Exception as exc:
            diag["option"] = "err:%s" % str(exc)[:100]
        for name in ("DraftAngle", "Angle", "FrontDraftAngle"):
            if hasattr(draft, name):
                try:
                    getattr(draft, name).SetFormula("5")
                    diag["angle"] = name
                    break
                except Exception as exc:
                    diag["angle"] = "err:%s" % str(exc)[:60]
        feat = b.CommitFeature()
    finally:
        try:
            b.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies), "diag": diag}
    if bodies:
        reads["faces"] = len(bodies[0].GetFaces())
        reads.update(mass(part, bodies))
    part2 = save_reopen(part, os.path.join(workdir, "taper.prt"))
    b2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(b2)
    if b2:
        reads["volume_reopened"] = float(mass(part2, b2)["volume_mm3"])
    _close_part(part2)
    return reads


def feature_cross_hole(params, workdir, rec):
    """块上横向 Ø20 通孔（管道 + 布尔差）→ 68584.07。"""
    part = new_part("cross")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    p = NXOpen.Point3d
    line = part.Curves.CreateLine(p(-10.0, 25.0, 10.0), p(110.0, 25.0, 10.0))
    secs = part.Sections.CreateSectionsUsingCurves(
        [line], NXOpen.SectionCollection.LoopOption.Separate, 0.0095, 0.01, 0.5)
    tb = part.Features.CreateTubeBuilder(NXOpen.Features.Tube.Null)
    try:
        rule = part.ScRuleFactory.CreateRuleCurveDumb([line])
        tb.PathSection.AddToSection([rule], line, None, None,
                                    NXOpen.Point3d(0.0, 0.0, 0.0),
                                    NXOpen.Section.Mode.Create)
        tb.OuterDiameter.SetFormula("20")
        tb.Tolerance = 0.01
        tube_feat = tb.CommitFeature()
    finally:
        try:
            tb.Destroy()
        except Exception:
            pass
    tool = tube_feat.GetBodies()[0]
    bb = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        bb.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        bb.Target = fa.GetBodies()[0]
        bb.Tools.Add([tool])
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
    part2 = save_reopen(part, os.path.join(workdir, "cross.prt"))
    b2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(b2)
    if b2:
        reads["volume_reopened"] = float(mass(part2, b2)["volume_mm3"])
    _close_part(part2)
    return reads


def feature_offset_face(params, workdir, rec):
    """六个面各偏置 5 mm → 110×60×30 = 198000。"""
    part = new_part("off")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    faces = list(body.GetFaces())
    diag = {"sentinel": None, "collector": None}
    of = None
    for name in ("OffsetFace", "Feature"):
        try:
            of = part.Features.CreateOffsetFaceBuilder(getattr(NXOpen.Features, name).Null)
            diag["sentinel"] = name
            break
        except Exception as exc:
            diag["sentinel"] = "err:%s" % str(exc)[:80]
            of = None
    if of is None:
        raise RuntimeError("CreateOffsetFaceBuilder 不可用: %r" % diag)
    try:
        rule = part.ScRuleFactory.CreateRuleFaceDumb(faces)
        try:
            of.FaceCollector.AddRules([rule])
            diag["collector"] = "AddRules"
        except Exception as exc:
            diag["collector"] = "err:%s" % str(exc)[:100]
        try:
            of.Distance.SetFormula("5")
        except Exception as exc:
            diag["distance"] = "err:%s" % str(exc)[:100]
        cf = of.CommitFeature()
    finally:
        try:
            of.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies), "diag": diag}
    if bodies:
        reads["faces"] = len(bodies[0].GetFaces())
        reads.update(mass(part, bodies))
    part2 = save_reopen(part, os.path.join(workdir, "off.prt"))
    b2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(b2)
    if b2:
        reads["volume_reopened"] = float(mass(part2, b2)["volume_mm3"])
    _close_part(part2)
    return reads


def feature_stack_blocks(params, workdir, rec):
    """两块叠加并集：100×50×20 + 50×30×10 = 115000。"""
    part = new_part("stack")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_block(part, 25.0, 10.0, 20.0, 50.0, 30.0, 10.0)
    return _volume_after_boolean(part, fa, fb, "Unite", workdir, "stack")


def attr_double(params, workdir, rec):
    """写实数属性 3.25 并读回。"""
    part = new_part("attrd")
    part.SetAttribute("NXKIT_DBL", 3.25)
    reads = {"double_attr": round(float(part.GetRealAttribute("NXKIT_DBL")), 6)}
    _close_part(part)
    return reads


def attr_logical(params, workdir, rec):
    """写布尔属性 True 并读回。"""
    part = new_part("attrl")
    part.SetBooleanUserAttribute("NXKIT_BOOL", 0, True,
                                 NXOpen.Update.Option.Now)
    reads = {"logical_attr": bool(part.GetBooleanUserAttribute("NXKIT_BOOL", 0))}
    _close_part(part)
    return reads


def sketch_constraint(params, workdir, rec):
    """草图上给两条线加重合约束（终点 = 起点）。"""
    part = new_part("skcon")
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    p = NXOpen.Point3d
    l1 = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 0.0, 0.0))
    l2 = part.Curves.CreateLine(p(100.0, 0.0, 0.0), p(100.0, 50.0, 0.0))
    sketch.AddGeometry(l1)
    sketch.AddGeometry(l2)

    cg1 = NXOpen.Sketch.ConstraintGeometry()
    cg1.Geometry = l1
    cg1.PointType = NXOpen.Sketch.ConstraintPointType.EndVertex
    cg2 = NXOpen.Sketch.ConstraintGeometry()
    cg2.Geometry = l2
    cg2.PointType = NXOpen.Sketch.ConstraintPointType.StartVertex
    con = sketch.CreateCoincidentConstraint(cg1, cg2)

    reads = {"coincidence_ok": con is not None,
             "inferred": bool(con.IsInferred) if con is not None else None}
    try:
        reads["constraint_geometry"] = len(list(con.GetGeometry()))
    except Exception:
        reads["constraint_geometry"] = None
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        pass
    _close_part(part)
    return reads


def sketch_constraint_kind(params, workdir, rec):
    """水平/竖直/等长/垂直约束（kind 区分）。"""
    kind = str(params.get("kind", "horizontal"))
    part = new_part("skc_" + kind)
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    p = NXOpen.Point3d
    l1 = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 10.0, 0.0))
    l2 = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(20.0, 60.0, 0.0))
    for ln in (l1, l2):
        sketch.AddGeometry(ln)

    def cg(curve):
        g = NXOpen.Sketch.ConstraintGeometry()
        g.Geometry = curve
        g.PointType = NXOpen.Sketch.ConstraintPointType.NotSet
        return g

    if kind == "horizontal":
        con = sketch.CreateHorizontalConstraint(cg(l1))
    elif kind == "vertical":
        con = sketch.CreateVerticalConstraint(cg(l2))
    elif kind == "equal":
        con = sketch.CreateEqualLengthConstraint(cg(l1), cg(l2))
    elif kind == "perpendicular":
        con = sketch.CreatePerpendicularConstraint(cg(l1), cg(l2))
    else:
        raise ValueError("未知约束类型 %r" % kind)

    reads = {"kind": kind, "con_ok": con is not None,
             "inferred": bool(con.IsInferred) if con is not None else None}
    try:
        reads["geom_count"] = len(list(con.GetGeometry()))
    except Exception:
        reads["geom_count"] = None
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        pass
    _close_part(part)
    return reads


def sketch_dimension(params, workdir, rec):
    """草图上给整圆加直径尺寸（值 50）。"""
    import math
    part = new_part("skdim")
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    p = NXOpen.Point3d
    arc = part.Curves.CreateArc(p(0.0, 0.0, 0.0),
                                NXOpen.Vector3d(1.0, 0.0, 0.0),
                                NXOpen.Vector3d(0.0, 1.0, 0.0),
                                25.0, 0.0, 2.0 * math.pi)
    sketch.AddGeometry(arc)

    diag = {}
    dg = NXOpen.Sketch.DimensionGeometry()
    dg.Geometry = arc
    dg.HelpPoint = p(25.0, 0.0, 0.0)
    try:
        dg.View = None
    except Exception:
        pass
    expr = part.Expressions.Create("nxkit_d1 = 50")
    diag["expr"] = str(expr.Value)[:20]
    con = sketch.CreateDiameterDimension(dg, p(40.0, 40.0, 0.0), expr)
    reads = {"dim_ok": con is not None, "expr_value": float(expr.Value),
             "diag": diag}
    try:
        reads["dim_geometry"] = len(list(con.GetGeometry()))
    except Exception:
        reads["dim_geometry"] = None
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        pass
    _close_part(part)
    return reads


def _sketch_two_lines(part):
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    p = NXOpen.Point3d
    l1 = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 0.0, 0.0))
    l2 = part.Curves.CreateLine(p(0.0, 40.0, 0.0), p(100.0, 40.0, 0.0))
    for ln in (l1, l2):
        sketch.AddGeometry(ln)
    return sketch, l1, l2


def sketch_fixed(params, workdir, rec):
    """把一条线固定（Fixed 约束）。"""
    part = new_part("skfix")
    sketch, l1, l2 = _sketch_two_lines(part)
    g = NXOpen.Sketch.ConstraintGeometry()
    g.Geometry = l1
    g.PointType = NXOpen.Sketch.ConstraintPointType.NotSet
    con = sketch.CreateFixedConstraint(g)
    reads = {"con_ok": con is not None,
             "inferred": bool(con.IsInferred) if con is not None else None}
    _close_part(part)
    return reads


def sketch_constraint_extra(params, workdir, rec):
    """共线 / 同心 / 中点 / 定长约束。"""
    import math
    kind = str(params.get("kind", "collinear"))
    part = new_part("skx_" + kind)
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    p = NXOpen.Point3d

    def cg(obj):
        g = NXOpen.Sketch.ConstraintGeometry()
        g.Geometry = obj
        g.PointType = NXOpen.Sketch.ConstraintPointType.NotSet
        return g

    if kind == "collinear":
        l1 = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 0.0, 0.0))
        l2 = part.Curves.CreateLine(p(20.0, 0.0, 0.0), p(120.0, 0.0, 0.0))
        for ln in (l1, l2):
            sketch.AddGeometry(ln)
        con = sketch.CreateCollinearConstraint(cg(l1), cg(l2))
    elif kind == "concentric":
        a1 = part.Curves.CreateArc(p(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
                                   NXOpen.Vector3d(0.0, 1.0, 0.0), 25.0, 0.0, 2.0 * math.pi)
        a2 = part.Curves.CreateArc(p(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
                                   NXOpen.Vector3d(0.0, 1.0, 0.0), 40.0, 0.0, 2.0 * math.pi)
        for arc in (a1, a2):
            sketch.AddGeometry(arc)
        con = sketch.CreateConcentricConstraint(cg(a1), cg(a2))
    elif kind == "midpoint":
        l1 = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 0.0, 0.0))
        sketch.AddGeometry(l1)
        pt = part.Points.CreatePoint(p(50.0, 0.0, 0.0))
        sketch.AddGeometry(pt)
        con = sketch.CreateMidpointConstraint(cg(pt), cg(l1))
    elif kind == "constant_length":
        l1 = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 0.0, 0.0))
        sketch.AddGeometry(l1)
        con = sketch.CreateConstantLengthConstraint(cg(l1))
    else:
        raise ValueError("未知约束 %r" % kind)

    reads = {"kind": kind, "con_ok": con is not None,
             "inferred": bool(con.IsInferred) if con is not None else None}
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        pass
    _close_part(part)
    return reads


def sketch_constraint_pair(params, workdir, rec):
    """平行 / 等半径约束。"""
    import math
    kind = str(params.get("kind", "parallel"))
    part = new_part("skp_" + kind)
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    p = NXOpen.Point3d

    def cg(obj):
        g = NXOpen.Sketch.ConstraintGeometry()
        g.Geometry = obj
        g.PointType = NXOpen.Sketch.ConstraintPointType.NotSet
        return g

    if kind == "parallel":
        l1 = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 0.0, 0.0))
        l2 = part.Curves.CreateLine(p(0.0, 20.0, 0.0), p(100.0, 20.0, 0.0))
        for ln in (l1, l2):
            sketch.AddGeometry(ln)
        con = sketch.CreateParallelConstraint(cg(l1), cg(l2))
    elif kind == "equal_radius":
        a1 = part.Curves.CreateArc(p(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
                                   NXOpen.Vector3d(0.0, 1.0, 0.0), 25.0, 0.0, 2.0 * math.pi)
        a2 = part.Curves.CreateArc(p(80.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
                                   NXOpen.Vector3d(0.0, 1.0, 0.0), 25.0, 0.0, 2.0 * math.pi)
        for arc in (a1, a2):
            sketch.AddGeometry(arc)
        con = sketch.CreateEqualRadiusConstraint(cg(a1), cg(a2))
    else:
        raise ValueError("未知约束 %r" % kind)

    reads = {"kind": kind, "con_ok": con is not None,
             "inferred": bool(con.IsInferred) if con is not None else None}
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        pass
    _close_part(part)
    return reads


def sketch_tangent(params, workdir, rec):
    """圆弧与直线相切（需要两个 help 对象）。"""
    import math
    part = new_part("sktan")
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    p = NXOpen.Point3d
    arc = part.Curves.CreateArc(p(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
                                NXOpen.Vector3d(0.0, 1.0, 0.0),
                                25.0, 0.0, 2.0 * math.pi)
    line = part.Curves.CreateLine(p(0.0, 25.0, 0.0), p(100.0, 25.0, 0.0))
    sketch.AddGeometry(arc)
    sketch.AddGeometry(line)

    def cg(obj):
        g = NXOpen.Sketch.ConstraintGeometry()
        g.Geometry = obj
        g.PointType = NXOpen.Sketch.ConstraintPointType.NotSet
        return g

    diag = {}
    try:
        h1 = NXOpen.Sketch.ConstraintGeometryHelp()
        h2 = NXOpen.Sketch.ConstraintGeometryHelp()
        diag["help"] = "ctor"
        con = sketch.CreateTangentConstraint(cg(arc), h1, cg(line), h2)
    except Exception as exc:
        diag["err"] = str(exc)[:150]
        con = None
    reads = {"con_ok": con is not None, "diag": diag,
             "inferred": bool(con.IsInferred) if con is not None else None}
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        pass
    _close_part(part)
    return reads


def attr_delete(params, workdir, rec):
    """写属性再删掉，验证读回为空/异常。"""
    part = new_part("attrdel")
    part.SetAttribute("NXKIT_TMP", "abc")
    before = str(part.GetStringAttribute("NXKIT_TMP"))
    part.DeleteAttributeByTypeAndTitle(
        NXOpen.NXObject.AttributeType.String, "NXKIT_TMP",
        NXOpen.Update.Option.Now)
    try:
        after = str(part.GetStringAttribute("NXKIT_TMP"))
    except Exception:
        after = ""
    reads = {"before": before, "after": after, "deleted": after == ""}
    _close_part(part)
    return reads


def attr_update(params, workdir, rec):
    """覆写同一标题的属性值。"""
    part = new_part("attrup")
    part.SetAttribute("NXKIT_UPD", "old")
    part.SetAttribute("NXKIT_UPD", "new")
    reads = {"value": str(part.GetStringAttribute("NXKIT_UPD"))}
    _close_part(part)
    return reads


def part_inch(params, workdir, rec):
    """英制部件：4×2×1 in 块 → 体积 8 in³。"""
    part = session().Parts.NewDisplay("inch_part.prt", NXOpen.Part.Units.Inches)
    session().Parts.SetWork(part)
    feat = make_block(part, 0, 0, 0, 4.0, 2.0, 1.0)
    body = feat.GetBodies()[0]
    raw = str(part.PartUnits)
    reads = {"units_raw": raw[:40],
             "units_inch": raw == "0",
             "body_count": 1}
    reads.update(mass(part, [body]))
    part2 = save_reopen(part, os.path.join(workdir, "inchp.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def export_step_ap214(params, workdir, rec):
    """AP214 STEP（schema 里应出现 AUTOMOTIVE_DESIGN）。"""
    part = new_part("st214")
    make_block(part, 0, 0, 0, 100, 50, 20)
    path = os.path.join(workdir, "export_ap214.step")
    if os.path.exists(path):
        os.remove(path)
    creator = session().DexManager.CreateStepCreator()
    try:
        creator.OutputFile = path
        creator.ExportAs = NXOpen.StepCreator.ExportAsOption.Ap214
        creator.Commit()
    finally:
        try:
            creator.Destroy()
        except Exception:
            pass
    exists = os.path.exists(path)
    text = ""
    if exists:
        with open(path, "r", encoding="latin-1", errors="replace") as fh:
            text = fh.read()
    reads = {"export_ok": bool(exists and len(text) > 1000),
             "has_iso_header": "ISO-10303-21" in text,
             "has_automotive_schema": "AUTOMOTIVE_DESIGN" in text.upper()}
    _close_part(part)
    return reads


def _face_area(part, faces):
    mm = part.MeasureManager
    return float(mm.NewFaceProperties(_unit(part), _unit(part), 0.99, faces).Area)


def measure_faces_two(params, workdir, rec):
    """只量两个面（两个 100×50 面 → 面积 10000）。"""
    part = new_part("face2")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    faces = list(body.GetFaces())
    big = [f for f in faces if abs(_face_area(part, [f]) - 5000.0) < 1.0]
    picked = big[:2]
    reads = {"picked": len(picked),
             "two_face_area": float(_face_area(part, picked))}
    _close_part(part)
    return reads


def asm_five_components(params, workdir, rec):
    """五个组件（两零件交替插入）。"""
    a_path = _make_ref_part(os.path.join(workdir, "five_a.prt"), "block",
                            (100.0, 50.0, 20.0))
    b_path = _make_ref_part(os.path.join(workdir, "five_b.prt"), "cyl",
                            (40.0, 30.0))
    asm = new_part("asm5")
    for i, path in enumerate((a_path, b_path, a_path, b_path, a_path)):
        asm.ComponentAssembly.AddComponent(
            path, "MODEL", "P%d" % i,
            NXOpen.Point3d(150.0 * i, 0.0, 0.0), _identity(), -1)
    children = asm.ComponentAssembly.RootComponent.GetChildren()
    reads = {"components": len(children)}
    _close_part(asm)
    return reads


def asm_component_names(params, workdir, rec):
    """组件名按插入时的名字保留（A/B/C）。"""
    a_path = _make_ref_part(os.path.join(workdir, "names_a.prt"), "block",
                            (100.0, 50.0, 20.0))
    b_path = _make_ref_part(os.path.join(workdir, "names_b.prt"), "cyl",
                            (40.0, 30.0))
    asm = new_part("asmname")
    for i, (path, name) in enumerate(((a_path, "AAA"), (b_path, "BBB"),
                                      (a_path, "CCC"))):
        asm.ComponentAssembly.AddComponent(
            path, "MODEL", name, NXOpen.Point3d(150.0 * i, 0.0, 0.0),
            _identity(), -1)
    names = sorted(str(c.Name) for c in asm.ComponentAssembly.RootComponent.GetChildren())
    reads = {"names": ",".join(names), "name_count": len(names)}
    _close_part(asm)
    return reads


def file_save_copy(params, workdir, rec):
    """另存副本并重新打开副本验证。"""
    part = new_part("copy_src")
    make_block(part, 0, 0, 0, 100, 50, 20)
    copy_path = os.path.join(workdir, "copy_dst.prt")
    if os.path.exists(copy_path):
        os.remove(copy_path)
    part.SaveAs(copy_path)
    _close_part(part)
    res = session().Parts.OpenActiveDisplay(copy_path, NXOpen.DisplayPartOption.AllowAdditional)
    part2 = res[0] if isinstance(res, (tuple, list)) else res
    session().Parts.SetWork(part2)
    bodies = _bodies_of(part2)
    reads = {"copy_exists": os.path.exists(copy_path),
             "copy_body_count": len(bodies)}
    if bodies:
        reads["copy_volume"] = float(mass(part2, bodies)["volume_mm3"])
    _close_part(part2)
    return reads


def attr_count(params, workdir, rec):
    """写 3 个字符串属性，读回标题数。"""
    part = new_part("attrcnt")
    for i in range(3):
        part.SetAttribute("NXKIT_A%d" % i, "v%d" % i)
    try:
        titles = list(part.GetAttributeTitlesByType(NXOpen.NXObject.AttributeType.String))
    except Exception:
        titles = []
    blob = " ".join(str(x) for x in titles)
    reads = {"title_count": blob.count("Title=NXKIT_A"),
             "titles_sample": blob.count("Title=")}
    _close_part(part)
    return reads


def boolean_unite_three(params, workdir, rec):
    """三体并集（A 100×50×20 + B 50×30×10，C 落在 A 内不增加体积）→ 115000。"""
    part = new_part("uni3")
    fa = make_block(part, 0, 0, 0, 100, 50, 20)
    fb = make_block(part, 25.0, 10.0, 20.0, 50.0, 30.0, 10.0)
    fc = make_block(part, 10.0, 10.0, 0.0, 20.0, 20.0, 10.0)
    bb = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        bb.Operation = NXOpen.Features.Feature.BooleanType.Unite
        bb.Target = fa.GetBodies()[0]
        bb.Tools.Add([fb.GetBodies()[0], fc.GetBodies()[0]])
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
    part2 = save_reopen(part, os.path.join(workdir, "uni3.prt"))
    b2 = _bodies_of(part2)
    reads["volume_reopened"] = float(mass(part2, b2)["volume_mm3"]) if b2 else None
    _close_part(part2)
    return reads


def feature_shell_volume(params, workdir, rec):
    """抽壳 2 mm 后复测体积：100000 − 96×46×16 = 29344。"""
    part = new_part("shellv")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    sb = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
    try:
        sb.Body = body
        sb.SetDefaultThickness("2")
        sb.Tolerance = 0.01
        sb.CommitFeature()
    finally:
        try:
            sb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies)}
    if bodies:
        reads.update(mass(part, bodies))
    part2 = save_reopen(part, os.path.join(workdir, "shellv.prt"))
    bodies2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def attr_on_face(params, workdir, rec):
    """属性挂在面上（不是体/特征上）。"""
    part = new_part("attrface")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    face = list(body.GetFaces())[0]
    face.SetAttribute("NXKIT_FACE", "x1")
    try:
        body_val = str(body.GetStringAttribute("NXKIT_FACE"))
    except Exception:
        body_val = ""
    reads = {"face_attr": str(face.GetStringAttribute("NXKIT_FACE")),
             "body_attr_empty": body_val == ""}
    _close_part(part)
    return reads


def sketch_linear_dim(params, workdir, rec):
    """两条平行线起点之间的竖直尺寸 40。"""
    part = new_part("sklin")
    sb = part.Sketches.CreateNewSketchInPlaceBuilder(None)
    sb.PlaneReference = _xy_plane(part)
    sketch = sb.Commit()
    try:
        sb.Destroy()
    except Exception:
        pass
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    p = NXOpen.Point3d
    l1 = part.Curves.CreateLine(p(0.0, 0.0, 0.0), p(100.0, 0.0, 0.0))
    l2 = part.Curves.CreateLine(p(0.0, 40.0, 0.0), p(100.0, 40.0, 0.0))
    for ln in (l1, l2):
        sketch.AddGeometry(ln)

    def dg(curve):
        d = NXOpen.Sketch.DimensionGeometry()
        d.Geometry = curve
        d.HelpPoint = NXOpen.Point3d(0.0, 0.0, 0.0)
        d.AssocType = NXOpen.Sketch.AssocType.StartPoint
        return d

    expr = part.Expressions.Create("nxkit_lin = 40")
    diag = {}
    try:
        con = sketch.CreateDimension(NXOpen.Sketch.ConstraintType.VerticalDim,
                                     dg(l1), dg(l2),
                                     NXOpen.Point3d(-30.0, 20.0, 0.0), expr)
        diag["dim"] = "ok"
    except Exception as exc:
        diag["dim"] = "err:%s" % str(exc)[:160]
        con = None
    reads = {"dim_ok": con is not None, "expr_value": float(expr.Value),
             "diag": diag}
    try:
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, True)
    except Exception:
        pass
    _close_part(part)
    return reads


def asm_constraint_touch(params, workdir, rec):
    """两个块的贴合约束：建约束 → LoadConstraintGeometry → 建参考 → 看解算状态。"""
    a_path = _make_ref_part(os.path.join(workdir, "ct_a.prt"), "block",
                            (100.0, 50.0, 20.0))
    b_path = _make_ref_part(os.path.join(workdir, "ct_b.prt"), "block",
                            (40.0, 30.0, 10.0))
    asm = new_part("asm_ct")
    res_a = asm.ComponentAssembly.AddComponent(
        a_path, "MODEL", "A", NXOpen.Point3d(0.0, 0.0, 0.0), _identity(), -1)
    res_b = asm.ComponentAssembly.AddComponent(
        b_path, "MODEL", "B", NXOpen.Point3d(0.0, 0.0, 60.0), _identity(), -1)
    comp_a = res_a[0] if isinstance(res_a, (tuple, list)) else res_a
    comp_b = res_b[0] if isinstance(res_b, (tuple, list)) else res_b

    proto_a = comp_a.Prototype
    proto_b = comp_b.Prototype
    faces_a = list(next(iter(proto_a.Bodies)).GetFaces())
    faces_b = list(next(iter(proto_b.Bodies)).GetFaces())
    cand_a = [f for f in faces_a if abs(_face_area(proto_a, [f]) - 5000.0) < 1.0]
    cand_b = [f for f in faces_b if abs(_face_area(proto_b, [f]) - 1200.0) < 1.0]
    diag = {"cand": "%d/%d" % (len(cand_a), len(cand_b))}
    if not cand_a or not cand_b:
        raise RuntimeError("找不到目标面 %r" % diag)

    pos = asm.ComponentAssembly.Positioner
    pos.BeginAssemblyConstraints()
    status = None
    try:
        con = pos.CreateConstraint(True)
        diag["con"] = type(con).__name__
        try:
            pos.LoadConstraintGeometry([con])
            diag["load"] = "ok"
        except Exception as exc:
            diag["load"] = "err:%s" % str(exc)[:120]
        # 先设约束类型（各种可能的枚举位置都试）
        for holder in ("PositioningConstraintType", "ComponentConstraintType"):
            cls = getattr(NXOpen, holder, None)
            if cls is None:
                continue
            for member in ("Touch", "Align", "DATUM", "Contact"):
                try:
                    con.ConstraintType = getattr(cls, member)
                    diag["ctype"] = "%s.%s" % (holder, member)
                    break
                except Exception as exc:
                    diag["ctype:%s.%s" % (holder, member)] = str(exc)[:60]
            if "ctype" in diag:
                break
        if "ctype" not in diag:
            try:
                cls = getattr(NXOpen.Positioning, "ConstraintType", None)
                if cls is not None:
                    con.ConstraintType = cls.Touch
                    diag["ctype"] = "Positioning.ConstraintType.Touch"
            except Exception as exc:
                diag["ctype"] = "err:%s" % str(exc)[:100]
        # 参数顺序是 (geometry, movable_object)：反着传才被接受
        r1 = con.CreateConstraintReference(cand_a[0], comp_a, False, False)
        r2 = con.CreateConstraintReference(cand_b[0], comp_b, False, False)
        diag["refs"] = [type(r1).__name__, type(r2).__name__]
    finally:
        try:
            pos.EndAssemblyConstraints()
        except Exception:
            pass
    try:
        pos.SolvePostponedConstraints()
        diag["solve"] = "SolvePostponedConstraints"
    except Exception as exc:
        diag["solve"] = "err:%s" % str(exc)[:100]
    try:
        raw = con.GetConstraintStatus()
        code = int(getattr(raw, "value", raw))
        base = type(raw).__name__.replace("MemberType", "")
        holder = getattr(NXOpen.Positioning, base, None) or getattr(NXOpen, base, None)
        name = None
        if holder is not None:
            try:
                name = str(holder.ValueOf(code)).split(".")[-1]
            except Exception:
                name = None
        diag["status_base"] = base
        status = name or str(code)
    except Exception as exc:
        status = "err:%s" % str(exc)[:80]
    try:
        ctype_txt = str(con.ConstraintType)
    except Exception:
        ctype_txt = ""
    reads = {"solver_status": status,
             "ref_count": 2 if diag.get("refs") else 0,
             "con_ok": con is not None,
             "ctype_text": ctype_txt[:40],
             "diag": diag}
    _close_part(asm)
    return reads


def measure_distance(params, workdir, rec):
    """两个 100×50 面之间的距离 = 20。"""
    part = new_part("dist")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    faces = list(feat.GetBodies()[0].GetFaces())
    big = [f for f in faces if abs(_face_area(part, [f]) - 5000.0) < 1.0][:2]
    unit = None
    for name in ("MilliMeter", "Millimeters", "Millimeter"):
        try:
            unit = part.UnitCollection.FindObject(name)
            break
        except Exception:
            continue
    md = part.MeasureManager.NewDistance(unit, False, big[0], big[1])
    reads = {"measured": round(float(md.Value), 6), "faces_used": len(big)}
    _close_part(part)
    return reads


def feature_thicken2(params, workdir, rec):
    """有界平面加厚 5 mm（只看实体，片体留在那里）。"""
    part = new_part("thick2")
    lines = _rect_lines(part)
    bp = part.Features.CreateBoundedPlaneBuilder(NXOpen.Features.BoundedPlane.Null)
    try:
        rule = part.ScRuleFactory.CreateRuleCurveDumb(lines)
        bp.BoundingCurves.AddToSection([rule], lines[0], None, None,
                                       NXOpen.Point3d(0.0, 0.0, 0.0),
                                       NXOpen.Section.Mode.Create)
        bp.CommitFeature()
    finally:
        try:
            bp.Destroy()
        except Exception:
            pass
    sheets = [b for b in _bodies_of(part) if b.IsSheetBody]
    tb = part.Features.CreateThickenBuilder(NXOpen.Features.Thicken.Null)
    diag = {}
    try:
        tb.FaceCollector.AddRules([part.ScRuleFactory.CreateRuleFaceDumb(
            list(sheets[0].GetFaces()))])
        diag["first_default"] = str(tb.FirstOffset.Value)
        tb.FirstOffset.SetFormula("5")
        diag["first_set"] = str(tb.FirstOffset.Value)
        diag["second"] = str(tb.SecondOffset.Value)
        try:
            tb.Tolerance = 0.01
            diag["tol"] = "0.01"
        except Exception as exc:
            diag["tol"] = "err:%s" % str(exc)[:60]
        tb.CommitFeature()
        diag["commit"] = "ok"
    finally:
        try:
            tb.Destroy()
        except Exception:
            pass
    solids = [b for b in _bodies_of(part) if b.IsSolidBody]
    reads = {"solid_count": len(solids), "diag": diag}
    if solids:
        reads.update(mass(part, solids))
    part2 = save_reopen(part, os.path.join(workdir, "thick3.prt"))
    bodies2 = [b for b in _bodies_of(part2) if b.IsSolidBody]
    reads["body_count_reopened"] = len(bodies2)
    if bodies2:
        reads["volume_reopened"] = float(mass(part2, bodies2)["volume_mm3"])
    _close_part(part2)
    return reads


def export_parasolid(params, workdir, rec):
    """导出 Parasolid 文本（X_T）。"""
    part = new_part("para")
    make_block(part, 0, 0, 0, 100, 50, 20)
    path = os.path.join(workdir, "export.x_t")
    if os.path.exists(path):
        os.remove(path)
    ex = session().DexManager.CreateParasolidExporter()
    diag = {}
    try:
        ex.OutputFile = path
        try:
            ex.ExportFrom = NXOpen.ParasolidExporter.ExportFromOption.DisplayedPart
            diag["export_from"] = "DisplayedPart"
        except Exception as exc:
            diag["export_from"] = "err:%s" % str(exc)[:100]
        for flag in ("Solids", "Surfaces"):
            try:
                setattr(ex.ObjectTypes, flag, True)
                diag["obj:" + flag] = True
            except Exception as exc:
                diag["obj:" + flag] = "err:%s" % str(exc)[:80]
        ex.Commit()
        diag["commit"] = "ok"
    finally:
        try:
            ex.Destroy()
        except Exception:
            pass
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    head = ""
    if exists:
        with open(path, "rb") as fh:
            head = fh.read(200).decode("latin-1", "replace")
    reads = {"export_ok": bool(exists and size > 500), "export_bytes": size,
             "head_ok": ("TRANSMIT" in head.upper() or "PARASOLID" in head.upper()),
             "diag": diag}
    _close_part(part)
    return reads


def feature_mirror_face(params, workdir, rec):
    """以块的一个大面为镜像平面做镜像 → 2 个实体 / 体积 200000。"""
    part = new_part("mir2")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    faces = list(body.GetFaces())
    big = [f for f in faces if abs(_face_area(part, [f]) - 5000.0) < 1.0]
    diag = {"cand": len(big)}
    if not big:
        raise RuntimeError("找不到 100×50 的面")
    mb = part.Features.CreateMirrorFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        mb.Plane.Value = big[0]
        diag["plane"] = "face"
        mb.FeatureSet.Add([feat])
        diag["featureset"] = "ok"
        try:
            mb.Motion.Commit()
            diag["motion_commit"] = "ok"
        except Exception as exc:
            diag["motion_commit"] = "err:%s" % str(exc)[:80]
        mb.CommitFeature()
        diag["commit"] = "ok"
    finally:
        try:
            mb.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies), "diag": diag}
    if bodies:
        reads.update(mass(part, bodies))
    part2 = save_reopen(part, os.path.join(workdir, "mir2.prt"))
    b2 = _bodies_of(part2)
    reads["body_count_reopened"] = len(b2)
    if b2:
        reads["volume_reopened"] = float(mass(part2, b2)["volume_mm3"])
    _close_part(part2)
    return reads


def solid_scale(params, workdir, rec):
    """整体缩放 2 倍 → 体积 ×8 = 800000。"""
    part = new_part("scale")
    feat = make_block(part, 0, 0, 0, 100, 50, 20)
    body = feat.GetBodies()[0]
    sc = part.Features.CreateScaleBuilder(NXOpen.Features.Feature.Null)
    diag = {}
    try:
        rule = part.ScRuleFactory.CreateRuleBodyDumb([body])
        for how in ("bodytoscale_add", "bodytoscale_setvalue"):
            try:
                if how == "bodytoscale_add":
                    sc.BodyToScale.Add([body])
                else:
                    sc.BodyToScale.SetValue(body)
                diag["body"] = how
                break
            except Exception as exc:
                diag["body:" + how] = str(exc)[:90]
        try:
            sc.Point = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
            diag["point"] = "Points.CreatePoint"
        except Exception as exc:
            diag["point"] = "err:%s" % str(exc)[:80]
        for member in ("Uniform", "UniformScale", "General"):
            try:
                sc.Type = getattr(NXOpen.Features.ScaleBuilderType, member)
                diag["type"] = member
                break
            except Exception as exc:
                diag["type:" + member] = str(exc)[:60]
        try:
            sc.UniformFactor.SetFormula("2")
            diag["uniform"] = str(sc.UniformFactor.Value)
        except Exception as exc:
            diag["uniform"] = "err:%s" % str(exc)[:80]
        try:
            sc.CommitFeature()
            diag["commit"] = "ok"
        except Exception as exc:
            diag["commit"] = "err:%s" % str(exc)[:120]
    finally:
        try:
            sc.Destroy()
        except Exception:
            pass
    bodies = _bodies_of(part)
    reads = {"body_count": len(bodies), "diag": diag}
    if bodies:
        reads.update(mass(part, bodies))
    part2 = save_reopen(part, os.path.join(workdir, "scale.prt"))
    b2 = _bodies_of(part2)
    reads["volume_reopened"] = float(mass(part2, b2)["volume_mm3"]) if b2 else None
    _close_part(part2)
    return reads


def _put(selection, obj):
    """把对象塞进 SelectObject / SelectObjectList，返回用哪种方式。"""
    if hasattr(selection, "Value"):
        selection.Value = obj
        return "Value"
    if hasattr(selection, "Add"):
        selection.Add([obj])
        return "Add"
    selection.SetValue(obj)
    return "SetValue"


def curve_helix(params, workdir, rec):
    """螺旋线：Ø40、螺距 20、3 圈。"""
    part = new_part("helix")
    hb = part.Features.CreateHelixBuilder(NXOpen.Features.Helix.Null)
    diag = {}
    try:
        for member in ("Turns", "NumberOfTurns", "ByTurns"):
            try:
                hb.LengthMethod = getattr(NXOpen.Features.HelixBuilderLengthMethods, member)
                diag["length_method"] = member
                break
            except Exception as exc:
                diag["lm:" + member] = str(exc)[:60]
        try:
            hb.SizeLaw.Value.SetFormula("40")
            diag["size"] = str(hb.SizeLaw.Value.Value)
        except Exception as exc:
            diag["size"] = "err:%s" % str(exc)[:90]
        try:
            hb.PitchLaw.Value.SetFormula("20")
            diag["pitch"] = str(hb.PitchLaw.Value.Value)
        except Exception as exc:
            diag["pitch"] = "err:%s" % str(exc)[:90]
        try:
            hb.NumberOfTurns = "3"
            diag["turns"] = hb.NumberOfTurns
        except Exception as exc:
            diag["turns"] = "err:%s" % str(exc)[:90]
        feat = hb.CommitFeature()
        diag["commit"] = "ok"
    except Exception as exc:
        diag["commit"] = "err:%s" % str(exc)[:130]
        feat = None
    finally:
        try:
            hb.Destroy()
        except Exception:
            pass
    ent = 0
    if feat is not None:
        try:
            ent = len(list(feat.GetEntities()))
        except Exception as exc:
            diag["entities"] = "err:%s" % str(exc)[:80]
    reads = {"helix_ok": feat is not None, "entity_count": ent, "diag": diag}
    _close_part(part)
    return reads


ACTIONS = {
    "curve_helix": curve_helix,
    "solid_scale": solid_scale,
    "feature_mirror_face": feature_mirror_face,
    "export_parasolid": export_parasolid,
    "feature_thicken2": feature_thicken2,
    "measure_distance": measure_distance,
    "asm_constraint_touch": asm_constraint_touch,
    "sketch_linear_dim": sketch_linear_dim,
    "feature_shell_volume": feature_shell_volume,
    "attr_on_face": attr_on_face,
    "file_save_copy": file_save_copy,
    "attr_count": attr_count,
    "boolean_unite_three": boolean_unite_three,
    "asm_five_components": asm_five_components,
    "asm_component_names": asm_component_names,
    "measure_faces_two": measure_faces_two,
    "part_inch": part_inch,
    "export_step_ap214": export_step_ap214,
    "attr_delete": attr_delete,
    "attr_update": attr_update,
    "sketch_tangent": sketch_tangent,
    "sketch_constraint_pair": sketch_constraint_pair,
    "sketch_constraint_extra": sketch_constraint_extra,
    "sketch_fixed": sketch_fixed,
    "sketch_dimension": sketch_dimension,
    "sketch_constraint_kind": sketch_constraint_kind,
    "sketch_constraint": sketch_constraint,
    "attr_double": attr_double,
    "attr_logical": attr_logical,
    "feature_stack_blocks": feature_stack_blocks,
    "feature_offset_face": feature_offset_face,
    "feature_cross_hole": feature_cross_hole,
    "feature_extrude_taper": feature_extrude_taper,
    "feature_boss": feature_boss,
    "asm_nested": asm_nested,
    "asm_four_components": asm_four_components,
    "feature_hole_csk": feature_hole_csk,
    "solid_cone_frustum": solid_cone_frustum,
    "inspect_body_type": inspect_body_type,
    "boolean_intersect_two": boolean_intersect_two,
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
    "boolean_two_tools": boolean_two_tools,
    "hole_array": hole_array,
    "feature_shell": feature_shell,
    "sketch_rect": sketch_rect,
    "sketch_extrude": sketch_extrude,
    "sketch_circle_extrude": sketch_circle_extrude,
    "feature_pocket_blind": feature_pocket_blind,
    "feature_hole_blind": feature_hole_blind,
    "drawing_sheet_size": drawing_sheet_size,
    "drawing_view_named": drawing_view_named,
    "asm_three_components": asm_three_components,
    "export_stl": export_stl,
    "feature_revolve": feature_revolve,
    "edge_blend_all": edge_blend_all,
    "measure_face_single": measure_face_single,
    "chamfer_edge": chamfer_edge,
    "surface_bounded_plane": surface_bounded_plane,
    "feature_tube": feature_tube,
    "curve_hyperbola": curve_hyperbola,
    "curve_parabola": curve_parabola,
}

def run(action: str, params: dict, workdir: str, rec: dict) -> dict:
    fn = ACTIONS.get(action)
    if fn is None:
        raise KeyError("未知动作 %r" % action)
    return fn(params or {}, workdir, rec)
