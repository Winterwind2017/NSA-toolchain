"""
cad_framework.sw_app - SolidWorks COM Application Wrapper

Provides high-level Python API for SolidWorks operations via pywin32 COM.
All implementations are based on real SolidWorks COM API patterns learned from
the Eduardof0nt/Solidworks-MCP-Server production-grade project.

Usage:
    with SolidWorksApp() as sw:
        sw.new_part()
        sw.create_sketch("Front Plane")
        sw.sketch_rectangle((0, 0), (100, 50))
        sw.exit_sketch()
        sw.extrude(depth=20)
        sw.save_document("part.SLDPRT")
"""

from typing import Optional, Any, List, Tuple, Dict, Union
import os
import sys
import math
import glob

from ..core.base import BaseCADApp
from ..core.errors import ConnectionError, DocumentError, DrawingError, NotSupportedError


# ═══════════════════════════════════════════════════════════════
#  SolidWorks Constants
# ═══════════════════════════════════════════════════════════════

# Document types
SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2
SW_DOC_DRAWING = 3

# End conditions
SW_END_BLIND = 0
SW_END_THROUGH_ALL = 1
SW_END_THROUGH_ALL_BOTH = 2
SW_END_MID_PLANE = 5
SW_END_UP_TO_VERTEX = 6
SW_END_UP_TO_SURFACE = 7

# Mate alignment
SW_MATE_ALIGNED = 0
SW_MATE_ANTI_ALIGNED = 1

# Mate types
SW_MATE_CONCENTRIC = 0
SW_MATE_COINCIDENT = 1
SW_MATE_DISTANCE = 2
SW_MATE_ANGLE = 3
SW_MATE_TANGENT = 4
SW_MATE_PARALLEL = 6
SW_MATE_PERPENDICULAR = 7

MATE_TYPE_MAP = {
    "CONCENTRIC": SW_MATE_CONCENTRIC,
    "COINCIDENT": SW_MATE_COINCIDENT,
    "DISTANCE": SW_MATE_DISTANCE,
    "ANGLE": SW_MATE_ANGLE,
    "TANGENT": SW_MATE_TANGENT,
    "PARALLEL": SW_MATE_PARALLEL,
    "PERPENDICULAR": SW_MATE_PERPENDICULAR,
}


# ═══════════════════════════════════════════════════════════════
#  Unit & Math Helpers
# ═══════════════════════════════════════════════════════════════

def _m(mm: float) -> float:
    """Millimeters to meters (SolidWorks COM uses meters)."""
    return mm / 1000.0


def _mm(m: float) -> float:
    """Meters to millimeters."""
    return m * 1000.0


def _r(deg: float) -> float:
    """Degrees to radians."""
    return deg * math.pi / 180.0


def _deg(rad: float) -> float:
    """Radians to degrees."""
    return rad * 180.0 / math.pi


# ═══════════════════════════════════════════════════════════════
#  SolidWorksApp class
# ═══════════════════════════════════════════════════════════════

class SolidWorksApp(BaseCADApp):
    """
    SolidWorks application controller via COM.
    All implementations use real SolidWorks COM API patterns.
    """

    _progids = [
        "SldWorks.Application",
        "SldWorks.Application.24",
        "SldWorks.Application.23",
        "SldWorks.Application.22",
        "SldWorks.Application.21",
    ]
    _app_name = "SolidWorks"

    def __init__(self, visible: bool = True, log_to_stdout: bool = True):
        super().__init__(visible=visible, log_to_stdout=log_to_stdout)
        self._nc = None  # Null callout variant cache

    # ─── Internal COM Access ──────────────────────────────────

    def _null_callout(self):
        """Get a cached VT_DISPATCH null variant for SelectByID2."""
        if self._nc is None:
            import pythoncom
            import win32com.client
            self._nc = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)
        return self._nc

    def _require_app(self):
        if not self._connected or self._com_obj is None:
            raise ConnectionError("SolidWorks not connected. Call connect() first.")
        return self._com_obj

    def _require_doc(self):
        doc = self._require_app().ActiveDoc
        if doc is None:
            raise DocumentError("No active document. Create or open one first.")
        return doc

    @property
    def _doc(self):
        return self._require_doc()

    @property
    def _sm(self):
        return self._doc.SketchManager

    @property
    def _fm(self):
        return self._doc.FeatureManager

    @property
    def _ext(self):
        return self._doc.Extension

    # ─── Template Discovery ──────────────────────────────────

    @staticmethod
    def _find_default_template(ext: str, prefer_gb: bool = True):
        """Find default SolidWorks template file."""
        search_patterns = [
            f"C:/ProgramData/SolidWorks/**/*.{ext}",
            f"C:/ProgramData/SOLIDWORKS/**/*.{ext}",
        ]
        all_found = []
        for pattern in search_patterns:
            all_found.extend(glob.glob(pattern, recursive=True))

        if not all_found:
            return ""

        gb = [f for f in all_found if "gb_" in os.path.basename(f).lower()]
        if gb and prefer_gb:
            return gb[0]

        top = [f for f in all_found if "MBD" not in f and "\\templates\\" in f]
        if top:
            return top[0]

        return all_found[0] if all_found else ""

    # ─── Connection ──────────────────────────────────────────

    def connect(self, force_launch: bool = False) -> bool:
        self._log("INFO", "Connecting...")
        try:
            import win32com.client
        except ImportError:
            raise ConnectionError("pywin32 not installed. Run: pip install pywin32")
        import pythoncom
        pythoncom.CoInitialize()

        # Try existing instance
        if not force_launch:
            for pid in self._progids:
                try:
                    self._com_obj = win32com.client.GetActiveObject(pid)
                    self._used_progid = pid
                    self._connected = True
                    self._log("INFO", f"Connected to running: {pid}")
                    self._post_connect()
                    return True
                except Exception:
                    continue

        # Launch new
        for pid in self._progids[:5]:
            try:
                self._com_obj = win32com.client.Dispatch(pid)
                self._used_progid = pid
                self._connected = True
                self._log("INFO", f"Launched: {pid}")
                self._post_connect()
                return True
            except Exception as e:
                self._log("DEBUG", f"Failed with {pid}: {e}")

        raise ConnectionError("Cannot connect to SolidWorks. Ensure it is installed.")

    def _post_connect(self):
        if self._visible:
            try:
                self._com_obj.Visible = True
            except Exception:
                pass

    def disconnect(self):
        self._com_obj = None
        self._connected = False
        self._nc = None
        self._log("INFO", "Disconnected")

    def quit_app(self):
        try:
            self._com_obj.ExitApp()
        except Exception as e:
            self._log("WARN", f"Quit failed: {e}")
        finally:
            self.disconnect()

    @property
    def com_obj(self):
        if not self._connected:
            raise ConnectionError("SolidWorks not connected.")
        return self._com_obj

    # ─── Document Operations ─────────────────────────────────

    def new_document(self, template_path: Optional[str] = None):
        if template_path:
            self._com_obj.NewDocument(template_path, 0, 0, 0)
        else:
            self.new_part()

    def new_part(self, template_path: Optional[str] = None):
        if not template_path:
            template_path = self._find_default_template("prtdot")
            if not template_path:
                raise DocumentError("Cannot find default part template (.prtdot)")
        self._com_obj.NewDocument(template_path, 0, 0, 0)
        self._log("INFO", "New part created")

    def new_assembly(self, template_path: Optional[str] = None):
        if not template_path:
            template_path = self._find_default_template("asmdot")
            if not template_path:
                raise DocumentError("Cannot find default assembly template (.asmdot)")
        self._com_obj.NewDocument(template_path, 0, 0, 0)
        self._log("INFO", "New assembly created")

    def new_drawing(self, template_path: Optional[str] = None):
        if not template_path:
            template_path = self._find_default_template("drwdot")
            if not template_path:
                raise DocumentError("Cannot find default drawing template (.drwdot)")
        self._com_obj.NewDocument(template_path, 0, 0, 0)
        self._log("INFO", "New drawing created")

    def open_document(self, filepath: str):
        if not os.path.exists(filepath):
            raise DocumentError(f"File not found: {filepath}")
        self._com_obj.OpenDoc6(filepath, 0, 0, "", 0, 0)
        self._log("INFO", f"Opened: {filepath}")

    def save_document(self, filepath: Optional[str] = None):
        doc = self._require_doc()
        if filepath:
            doc.SaveAs3(filepath, 0, 0)
            self._log("INFO", f"Saved as: {filepath}")
        else:
            doc.Save()
            self._log("INFO", "Saved")

    def close_document(self, save: bool = True):
        doc = self._require_doc()
        name = doc.GetTitle()
        self._com_obj.CloseDoc(name)
        self._log("INFO", f"Closed: {name} (save={save})")

    def close_all_documents(self):
        self._com_obj.CloseAllDocuments(True)
        self._log("INFO", "All documents closed")

    def get_active_document_name(self) -> str:
        doc = self._com_obj.ActiveDoc
        if not doc:
            return ""
        try:
            return doc.GetTitle()
        except TypeError:
            return doc.GetTitle

    def get_active_document_path(self) -> str:
        doc = self._com_obj.ActiveDoc
        return doc.GetPathName() if doc else ""

    def list_open_documents(self) -> List[dict]:
        result = []
        count = self._com_obj.GetDocumentCount()
        for i in range(count):
            doc = self._com_obj.GetOpenDocument(str(i % count))
            if doc:
                result.append({
                    "title": doc.GetTitle(),
                    "path": doc.GetPathName(),
                })
        return result

    # ─── Export ──────────────────────────────────────────────

    def export_pdf(self, filepath: str, **kwargs):
        doc = self._require_doc()
        doc.SaveAs3(filepath, 0, 0)
        self._log("INFO", f"Exported PDF: {filepath}")

    def export_dxf(self, filepath: str):
        doc = self._require_doc()
        doc.SaveAs3(filepath, 0, 0)
        self._log("INFO", f"Exported DXF: {filepath}")

    def export_step(self, filepath: str):
        doc = self._require_doc()
        doc.SaveAs3(filepath, 0, 0)
        self._log("INFO", f"Exported STEP: {filepath}")

    def export_iges(self, filepath: str):
        doc = self._require_doc()
        doc.SaveAs3(filepath, 0, 0)
        self._log("INFO", f"Exported IGES: {filepath}")

    def export_stl(self, filepath: str):
        doc = self._require_doc()
        doc.SaveAs3(filepath, 0, 0)
        self._log("INFO", f"Exported STL: {filepath}")

    # ═══════════════════════════════════════════════════════════
    #  SKETCH OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def create_sketch(self, plane: str = "Front Plane"):
        """Create a sketch on a reference plane. Uses FeatureByName for robustness."""
        doc = self._require_doc()
        feat = doc.FeatureByName(plane)
        if feat:
            feat.Select2(False, 0)
        else:
            doc.Extension.SelectByID2(plane, "PLANE", 0, 0, 0, False, 0, self._null_callout(), 0)
        doc.SketchManager.InsertSketch(True)
        self._log("DEBUG", f"Sketch created on: {plane}")

    def exit_sketch(self):
        """Exit the current sketch."""
        self._require_doc().SketchManager.InsertSketch(True)
        self._log("DEBUG", "Sketch exited")

    def close_sketch(self):
        self.exit_sketch()

    def edit_sketch(self, sketch_name: str):
        """Edit an existing sketch."""
        doc = self._require_doc()
        doc.Extension.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0, self._null_callout(), 0)
        doc.MenuCommand(2026)  # swCommands_Sketch_Edit
        self._log("DEBUG", f"Editing sketch: {sketch_name}")

    def list_sketches(self) -> List[str]:
        doc = self._require_doc()
        sketches = []
        for feat in doc.FeatureManager.GetFeatureCount(0, True):
            pass
        # Iterate feature tree
        feat = doc.FeatureManager.FirstFeature()
        while feat:
            if feat.GetTypeName2() == "ProfileFeature":
                sketches.append(feat.Name)
            feat = feat.GetNextFeature()
        return sketches

    # ─── Sketch Primitives ──────────────────────────────────

    def sketch_line(self, start: Tuple[float, float],
                    end: Tuple[float, float]):
        """Draw a line in the active sketch."""
        sm = self._sm
        seg = sm.CreateLine(
            _m(start[0]), _m(start[1]), 0.0,
            _m(end[0]), _m(end[1]), 0.0,
        )
        if seg is None:
            raise DrawingError("Failed to create line. Ensure a sketch is active.")
        self._log("DEBUG", f"Line: {start} -> {end}")

    def sketch_circle(self, center: Tuple[float, float], radius: float):
        """Draw a circle by radius in the active sketch."""
        sm = self._sm
        seg = sm.CreateCircleByRadius(
            _m(center[0]), _m(center[1]), 0.0, _m(radius),
        )
        if seg is None:
            raise DrawingError("Failed to create circle. Ensure a sketch is active.")
        self._log("DEBUG", f"Circle: center={center}, r={radius}")

    def sketch_rectangle(self, p1: Tuple[float, float],
                         p2: Tuple[float, float],
                         rect_type: str = "corner"):
        """
        Draw a rectangle in the active sketch.

        Args:
            p1, p2: Corner points (or center+corner for 'center' type)
            rect_type: 'corner' (default) or 'center'
        """
        sm = self._sm
        x1, y1 = p1
        x2, y2 = p2
        if rect_type == "center":
            segs = sm.CreateCenterRectangle(
                _m(x1), _m(y1), 0.0, _m(x2), _m(y2), 0.0,
            )
        else:
            segs = sm.CreateCornerRectangle(
                _m(x1), _m(y1), 0.0, _m(x2), _m(y2), 0.0,
            )
        if segs is None:
            raise DrawingError("Failed to create rectangle. Ensure a sketch is active.")
        self._log("DEBUG", f"Rectangle: {p1} - {p2}")

    def sketch_arc(self, center: Tuple[float, float],
                   start_angle_deg: float, end_angle_deg: float,
                   radius: float, clockwise: bool = False):
        """Draw an arc by center, radius, and angles."""
        cx, cy = center
        sa = _r(start_angle_deg)
        ea = _r(end_angle_deg)
        r = _m(radius)
        sx = _m(cx) + r * math.cos(sa)
        sy = _m(cy) + r * math.sin(sa)
        ex = _m(cx) + r * math.cos(ea)
        ey = _m(cy) + r * math.sin(ea)
        direction = -1 if clockwise else 1
        seg = self._sm.CreateArc(
            _m(cx), _m(cy), 0.0,
            sx, sy, 0.0,
            ex, ey, 0.0,
            direction,
        )
        if seg is None:
            raise DrawingError("Failed to create arc. Ensure a sketch is active.")
        self._log("DEBUG", f"Arc: center={center}, r={radius}")

    def sketch_ellipse(self, center: Tuple[float, float],
                       semi_major: float, semi_minor: float,
                       rotation_deg: float = 0.0):
        """Draw an ellipse by center and semi-axes."""
        cx, cy = center
        rot = _r(rotation_deg)
        ax = _m(cx) + _m(semi_major) * math.cos(rot)
        ay = _m(cy) + _m(semi_major) * math.sin(rot)
        bx = _m(cx) + _m(semi_minor) * math.cos(rot + math.pi / 2)
        by = _m(cy) + _m(semi_minor) * math.sin(rot + math.pi / 2)
        seg = self._sm.CreateEllipse(
            _m(cx), _m(cy), 0.0,
            ax, ay, 0.0,
            bx, by, 0.0,
        )
        if seg is None:
            raise DrawingError("Failed to create ellipse. Ensure a sketch is active.")
        self._log("DEBUG", f"Ellipse: center={center}")

    def sketch_polygon(self, center: Tuple[float, float],
                       num_sides: int, circumscribed_radius: float,
                       rotation_deg: float = 0.0):
        """Draw a regular polygon."""
        cx, cy = center
        rot = _r(rotation_deg)
        vx = _m(cx) + _m(circumscribed_radius) * math.cos(rot)
        vy = _m(cy) + _m(circumscribed_radius) * math.sin(rot)
        segs = self._sm.CreatePolygon(
            _m(cx), _m(cy), 0.0, vx, vy, 0.0,
            num_sides, True,
        )
        if segs is None:
            raise DrawingError("Failed to create polygon. Ensure a sketch is active.")
        self._log("DEBUG", f"Polygon: {num_sides} sides")

    def sketch_spline(self, points: List[Tuple[float, float]]):
        """Draw a spline through fit points."""
        flat_pts = []
        for x, y in points:
            flat_pts.extend([_m(x), _m(y), 0.0])
        seg = self._sm.CreateSpline(flat_pts)
        if seg is None:
            raise DrawingError("Failed to create spline. Ensure a sketch is active.")
        self._log("DEBUG", f"Spline: {len(points)} pts")

    def sketch_centerline(self, start: Tuple[float, float],
                          end: Tuple[float, float]):
        """Draw a centerline (construction line) in the active sketch."""
        seg = self._sm.CreateLine(
            _m(start[0]), _m(start[1]), 0.0,
            _m(end[0]), _m(end[1]), 0.0,
        )
        if seg:
            seg.ConstructionGeometry = True
        self._log("DEBUG", f"Centerline: {start} - {end}")

    def sketch_offset(self, distance: float, outward: bool = True):
        """Offset selected sketch entities."""
        segs = self._sm.SketchOffset2(
            _m(distance), outward, True, False, None, None,
        )
        if segs is None:
            raise DrawingError("Offset failed. Select sketch entities first.")
        self._log("DEBUG", f"Sketch offset: d={distance}")

    # ─── Sketch Constraints & Dimensions ────────────────────

    def add_sketch_constraint(self, relation_type: str):
        """
        Add a geometric relation to selected sketch entities.

        Args:
            relation_type: 'horizontal', 'vertical', 'parallel', 'perpendicular',
                         'tangent', 'equal', 'concentric', 'coincident', 'fix'
        """
        rel_map = {
            "horizontal": 1,
            "vertical": 2,
            "parallel": 3,
            "perpendicular": 4,
            "tangent": 5,
            "concentric": 7,
            "coincident": 8,
            "equal": 9,
            "fix": 17,
        }
        rel = rel_map.get(relation_type.lower())
        if rel is None:
            raise DrawingError(f"Unknown relation: {relation_type}")
        sm = self._sm
        result = sm.AddRelation(rel)
        if not result:
            raise DrawingError(
                f"Failed to add '{relation_type}' relation. "
                "Select the appropriate entities first."
            )
        self._log("DEBUG", f"Constraint: {relation_type}")

    def add_sketch_dimension(self, value: float, x: float = 0.0, y: float = 0.0):
        """Add a smart dimension to selected sketch entities."""
        sm = self._sm
        result = sm.AddDimension(x, y)
        if result is None:
            raise DrawingError("Failed to add dimension. Select entities first.")
        # Set the dimension value
        try:
            result.SetValue3(_m(value), 0)
        except Exception:
            pass
        self._log("DEBUG", f"Dimension: {value}")

    # ═══════════════════════════════════════════════════════════
    #  PART FEATURES
    # ═══════════════════════════════════════════════════════════

    def extrude(self, depth: float, direction: str = "blind",
                flip_direction: bool = False, draft_angle: float = 0.0,
                is_cut: bool = False):
        """
        Extrude the active sketch.

        Args:
            depth: Extrusion depth in mm
            direction: 'blind', 'through_all', 'through_all_both',
                      'mid_plane', 'up_to_vertex', 'up_to_surface'
            flip_direction: Flip extrusion direction
            draft_angle: Draft angle in degrees
            is_cut: If True, performs a cut extrude
        """
        doc = self._require_doc()
        fm = doc.FeatureManager

        end_cond = {
            "blind": SW_END_BLIND,
            "through_all": SW_END_THROUGH_ALL,
            "through_all_both": SW_END_THROUGH_ALL_BOTH,
            "mid_plane": SW_END_MID_PLANE,
            "up_to_vertex": SW_END_UP_TO_VERTEX,
            "up_to_surface": SW_END_UP_TO_SURFACE,
        }.get(direction.lower(), SW_END_BLIND)

        draft_on = draft_angle > 0
        ang = _r(draft_angle) if draft_on else 0.0

        feat = None
        for extra in [
            (False, False, False),  # 23 params (SW 2024)
            (False, False),  # 22 params
            (),
        ]:
            try:
                args = [
                    True, is_cut, flip_direction,
                    end_cond, SW_END_BLIND,
                    _m(depth), 0.0,
                    False, False,
                    draft_on, False,
                    ang, 0.0,
                    False, False,
                    False, False,
                    True, False, True,
                ] + list(extra)
                feat = fm.FeatureExtrusion3(*args)
                if feat is not None:
                    break
            except Exception:
                pass

        if feat is None:
            raise DrawingError(
                "Extrude failed. Ensure a closed sketch profile is selected. "
                "Try direction='through_all' for cuts."
            )
        self._log("INFO", f"Extrude: depth={depth}, cut={is_cut}")
        return feat

    def cut_extrude(self, depth: float, **kwargs):
        """Cut extrude (remove material)."""
        return self.extrude(depth=depth, is_cut=True, **kwargs)

    def revolve(self, angle: float = 360.0, is_cut: bool = False,
                flip_direction: bool = False):
        """Revolve the active sketch around a centerline."""
        doc = self._require_doc()
        feat = doc.FeatureManager.FeatureRevolve2(
            _r(angle), 0.0, SW_END_BLIND, SW_END_BLIND,
            False, True, True, flip_direction,
            0.0, False, True, True,
        )
        if feat is None:
            raise DrawingError(
                "Revolve failed. Ensure a sketch profile and a centerline are selected."
            )
        self._log("INFO", f"Revolve: {angle} deg, cut={is_cut}")
        return feat

    def fillet(self, radius: float, tangent_propagation: bool = True):
        """Add a fillet to selected edges."""
        doc = self._require_doc()
        feat = doc.FeatureManager.FeatureFillet(
            _m(radius), True, tangent_propagation, False, False, 0.0, 0,
        )
        if feat is None:
            raise DrawingError("Fillet failed. Select edges first.")
        self._log("INFO", f"Fillet: r={radius}")
        return feat

    def chamfer(self, distance: float, angle: float = 45.0):
        """Add a chamfer to selected edges (distance-angle method)."""
        doc = self._require_doc()
        feat = doc.FeatureManager.InsertFeatureChamfer(
            1, 0, _m(distance), _r(angle), False, False, False, False,
        )
        if feat is None:
            # Fallback to equal-distance
            feat = doc.FeatureManager.InsertFeatureChamfer(
                0, 0, _m(distance), 0.0, False, False, False, False,
            )
        if feat is None:
            raise DrawingError("Chamfer failed. Select edges first.")
        self._log("INFO", f"Chamfer: d={distance}, a={angle}")
        return feat

    def shell(self, thickness: float, outward: bool = False):
        """Shell a solid body. Select faces to remove first."""
        doc = self._require_doc()
        feat = doc.FeatureManager.FeatureShell(
            _m(thickness), outward, None,
        )
        if feat is None:
            raise DrawingError("Shell failed. Select face(s) to remove first.")
        self._log("INFO", f"Shell: thickness={thickness}")
        return feat

    def draft(self, draft_angle: float):
        """Add a draft angle. Select neutral plane and draught faces first."""
        doc = self._require_doc()
        feat = doc.FeatureManager.FeatureDraft2(
            True, False, _r(draft_angle), True,
        )
        if feat is None:
            raise DrawingError(
                "Draft failed. Select the neutral plane and draught faces first."
            )
        self._log("INFO", f"Draft: angle={draft_angle}")
        return feat

    # ─── Hole Wizard ────────────────────────────────────────

    def hole_wizard(self, hole_type: str = "simple", size: str = "",
                    depth: float = 10.0, through_all: bool = False,
                    x: float = 0.0, y: float = 0.0,
                    standard_index: int = 1, fastener_type: int = 0):
        """
        Create a hole using Hole Wizard.

        Args:
            hole_type: 'simple', 'counterbore', 'countersink',
                      'straight_tap', 'tapered_tap'
            size: Thread/size spec
            depth: Hole depth in mm
            through_all: Drill through all
            x, y: Position relative to selected face
        """
        doc = self._require_doc()
        end_cond = SW_END_THROUGH_ALL if through_all else SW_END_BLIND
        # 真常量（从 sldworks.tlb 的 swWzd* 读出来的）：
        #   swWzdCounterBore=0 / swWzdCounterSink=1 / swWzdHole=2 / swWzdTap=4
        # 旧映射把 "simple" 写成 0 —— 那其实是**沉头孔**，所以我们一直在建沉头孔。
        hole_type_map = {
            "simple": 2, "counterbore": 0, "countersink": 1,
            "straight_tap": 4, "tapered_tap": 4,
        }
        wh_type = hole_type_map.get(hole_type.lower(), 0)
        # HoleWizard5 的真签名是 **27 参**（从 sldworks.tlb 读出来的顺序）：
        #   GenericHoleType, StandardIndex, FastenerTypeIndex, SSize(BSTR),
        #   EndType, Diameter, Depth, Length, Value1..Value12,
        #   ThreadClass(BSTR), RevDir, FeatureScope, AutoSelect,
        #   AssemblyFeatureScope, AutoSelectComponents, PropagateFeatureToParts
        # 旧代码只传了 14 个且从第 3 个起就错位：StandardIndex 落成 0（=ANSI 英寸）、
        # SSize 位置塞的是深度数值、Diameter=0（用默认）→ SW 就按「英寸 + 默认 2″」
        # 造出 Ø50.8 的孔。这就是"孔向导几何恒 Ø50.8"的真正原因。
        feat = doc.FeatureManager.HoleWizard5(
            wh_type,                      # 1 GenericHoleType
            int(standard_index),          # 2 StandardIndex（1 = ANSI Metric）
            int(fastener_type),           # 3 FastenerTypeIndex
            str(size or ""),              # 4 SSize（"M6" 这种字符串）
            int(end_cond),                # 5 EndType
            0.0,                          # 6 Diameter（0 = 由标准库决定）
            _m(depth),                    # 7 Depth
            0.0,                          # 8 Length
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 9-20 Value1..Value12
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            "",                           # 21 ThreadClass
            True,                         # 22 RevDir
            True,                         # 23 FeatureScope
            True,                         # 24 AutoSelect
            False,                        # 25 AssemblyFeatureScope
            False,                        # 26 AutoSelectComponents
            False,                        # 27 PropagateFeatureToParts
        )
        if feat is None:
            raise DrawingError(
                "Hole Wizard failed. Select a face to place the hole on."
            )
        self._log("INFO", f"Hole Wizard: type={hole_type}, through_all={through_all}")
        return feat

    # ─── Sweep & Loft ───────────────────────────────────────

    def sweep(self, is_cut: bool = False, merge_result: bool = True):
        """
        Sweep a profile along a path. Select profile then path first.

        Args:
            is_cut: If True, performs a cut sweep
            merge_result: Merge with existing bodies
        """
        doc = self._require_doc()
        feat = doc.FeatureManager.InsertProtrusionSwept4(
            False, False, 0, 0, 0.0,
            True, False, False,
            merge_result,
            False, False, 0.0, 0.0,
        )
        if feat is None:
            raise DrawingError(
                "Sweep failed. Select the profile sketch and path sketch first."
            )
        self._log("INFO", f"Sweep: cut={is_cut}")
        return feat

    def loft(self, is_cut: bool = False, close_loft: bool = False):
        """
        Create a loft between multiple profiles.
        Select profiles in order first.

        Args:
            is_cut: If True, performs a cut loft
            close_loft: Close the loft back to the first profile
        """
        doc = self._require_doc()
        feat = doc.FeatureManager.InsertProtrusionBlend2(
            close_loft, True, True, 1, 0.0, 0.0,
            False, False, True, True,
            0, 0, True, True,
        )
        if feat is None:
            raise DrawingError(
                "Loft failed. Select two or more sketch profiles in order."
            )
        self._log("INFO", f"Loft: cut={is_cut}")
        return feat

    # ─── Patterns ───────────────────────────────────────────

    def linear_pattern(self, dir1_count: int, dir1_spacing: float,
                       dir2_count: int = 1, dir2_spacing: float = 10.0,
                       geometry_pattern: bool = False):
        """
        Create a linear pattern.

        Args:
            dir1_count: Number in first direction
            dir1_spacing: Spacing in first direction (mm)
            dir2_count: Number in second direction
            dir2_spacing: Spacing in second direction (mm)
            geometry_pattern: Pattern as geometry only
        """
        doc = self._require_doc()
        feat = doc.FeatureManager.FeatureLinearPattern3(
            dir1_count, _m(dir1_spacing),
            dir2_count, _m(dir2_spacing),
            True, True, geometry_pattern,
            0, 0, True,
        )
        if feat is None:
            raise DrawingError(
                "Linear pattern failed. Select a feature and direction edges first."
            )
        self._log("INFO", f"Linear pattern: {dir1_count}x{dir2_count}")
        return feat

    def circular_pattern(self, count: int, angle: float = 360.0,
                         geometry_pattern: bool = False):
        """Create a circular pattern. Select feature and axis first."""
        doc = self._require_doc()
        feat = doc.FeatureManager.FeatureCirPattern3(
            count, _r(angle), True, geometry_pattern,
            0, True,
        )
        if feat is None:
            raise DrawingError(
                "Circular pattern failed. Select a feature and axis/face first."
            )
        self._log("INFO", f"Circular pattern: {count}x @ {angle}deg")
        return feat

    def mirror_feature(self, mirror_plane: str):
        """Mirror a feature across a plane. Select features to mirror first."""
        doc = self._require_doc()
        doc.Extension.SelectByID2(
            mirror_plane, "PLANE", 0, 0, 0, True, 32,
            self._null_callout(), 0,
        )
        feat = doc.FeatureManager.InsertMirrorFeature2(
            True, False, True, True, False,
        )
        if feat is None:
            raise DrawingError("Mirror failed. Select features to mirror first.")
        self._log("INFO", f"Mirror: across {mirror_plane}")
        return feat

    # ─── Feature Management ─────────────────────────────────

    def list_features(self) -> List[Dict[str, Any]]:
        """List all features in the active part."""
        doc = self._require_doc()
        results = []
        feat = doc.FeatureManager.FirstFeature()
        while feat:
            try:
                results.append({
                    "name": feat.Name,
                    "type": feat.GetTypeName2(),
                    "suppressed": feat.IsSuppressed2(),
                })
            except Exception:
                results.append({"name": str(feat), "type": "unknown"})
            feat = feat.GetNextFeature()
        return results

    def delete_feature(self, feature_name: str, absorb_children: bool = False):
        """Delete a feature by name."""
        doc = self._require_doc()
        doc.Extension.SelectByID2(
            feature_name, "BODYFEATURE", 0, 0, 0,
            False, 0, self._null_callout(), 0,
        )
        doc.Extension.DeleteSelection2(0 if absorb_children else 1)
        self._log("INFO", f"Deleted: {feature_name}")

    def suppress_feature(self, feature_name: str):
        """Suppress a feature."""
        doc = self._require_doc()
        doc.Extension.SelectByID2(
            feature_name, "BODYFEATURE", 0, 0, 0,
            False, 0, self._null_callout(), 0,
        )
        doc.EditSuppress2()
        self._log("INFO", f"Suppressed: {feature_name}")

    def unsuppress_feature(self, feature_name: str):
        """Unsuppress a feature."""
        doc = self._require_doc()
        doc.Extension.SelectByID2(
            feature_name, "BODYFEATURE", 0, 0, 0,
            False, 0, self._null_callout(), 0,
        )
        doc.EditUnsuppress2()
        self._log("INFO", f"Unsuppressed: {feature_name}")

    # ═══════════════════════════════════════════════════════════
    #  ASSEMBLY OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def insert_component(self, file_path: str,
                         x: float = 0.0, y: float = 0.0, z: float = 0.0,
                         fixed: bool = False):
        """Insert a component into the active assembly."""
        doc = self._require_doc()
        # IAssemblyDoc::AddComponent5 是 **8 参**：
        #   (CompConfig, UseConfigForPart, NewPartPath, ConfigOption,
        #    InsertedOption, X, Y, Z)
        # 以前写成 7 参（把 file_path 当第一个参数），晚绑定报
        # "非选择性的参数" → 返回 None → 所有装配插入都失败。
        comp = doc.AddComponent5(
            "", False, file_path, 0, 0,
            _m(x), _m(y), _m(z),
        )
        if comp is None:
            raise DocumentError(
                f"Failed to insert '{file_path}'. "
                "Ensure the file exists and the active document is an assembly."
            )
        self._log("INFO", f"Component added: {comp.Name2}")
        return comp

    def add_mate(self, mate_type: str, entity1: str, entity2: str,
                 distance_or_angle: Optional[float] = None,
                 flip_mate: bool = False):
        """
        Add an assembly mate between two entities.

        Args:
            mate_type: 'CONCENTRIC', 'COINCIDENT', 'DISTANCE', 'ANGLE',
                      'TANGENT', 'PARALLEL', 'PERPENDICULAR'
            entity1, entity2: Entity references (e.g. 'Face@Part1-1')
            distance_or_angle: Value for distance/angle mates
            flip_mate: Anti-aligned when True
        """
        doc = self._require_doc()
        mt = MATE_TYPE_MAP.get(mate_type.upper())
        if mt is None:
            raise DrawingError(
                f"Unknown mate type '{mate_type}'. "
                f"Valid: {', '.join(MATE_TYPE_MAP.keys())}"
            )

        # Select entities
        doc.ClearSelection2(True)
        for ent in [entity1, entity2]:
            parts = ent.rsplit("/", 1)
            ref_name = parts[1] if len(parts) == 2 else ent
            doc.Extension.SelectByID2(
                ref_name, "FACE", 0, 0, 0,
                True, 1, self._null_callout(), 0,
            )

        align = SW_MATE_ANTI_ALIGNED if flip_mate else SW_MATE_ALIGNED
        dist = _m(distance_or_angle) if distance_or_angle and mt == SW_MATE_DISTANCE else 0.0
        ang = _r(distance_or_angle) if distance_or_angle and mt == SW_MATE_ANGLE else 0.0

        feat = doc.AddMate5(
            mt, align, flip_mate,
            dist, dist, 0.0,
            1.0, 1.0,
            ang, ang, 0.0,
            False, False, False,
        )

        if isinstance(feat, tuple):
            feat, err = feat[0], feat[1]
        if feat is None:
            raise DrawingError(f"Mate '{mate_type}' failed.")
        self._log("INFO", f"Mate: {mate_type}")
        return feat

    def mate_concentric(self, entity1: str, entity2: str):
        self.add_mate("CONCENTRIC", entity1, entity2)

    def mate_coincident(self, entity1: str, entity2: str):
        self.add_mate("COINCIDENT", entity1, entity2)

    def mate_distance(self, entity1: str, entity2: str, distance: float):
        self.add_mate("DISTANCE", entity1, entity2, distance_or_angle=distance)

    def mate_parallel(self, entity1: str, entity2: str):
        self.add_mate("PARALLEL", entity1, entity2)

    def mate_perpendicular(self, entity1: str, entity2: str):
        self.add_mate("PERPENDICULAR", entity1, entity2)

    def mate_tangent(self, entity1: str, entity2: str):
        self.add_mate("TANGENT", entity1, entity2)

    def mate_angle(self, entity1: str, entity2: str, angle: float):
        self.add_mate("ANGLE", entity1, entity2, distance_or_angle=angle)

    def fix_component(self, component_name: str, fix: bool = True):
        """Fix or float a component."""
        doc = self._require_doc()
        doc.Extension.SelectByID2(
            component_name, "COMPONENT", 0, 0, 0,
            False, 0, self._null_callout(), 0,
        )
        if fix:
            doc.EditMakeRigid()
        else:
            doc.EditMakeFlexible()
        self._log("INFO", f"Component '{component_name}' fixed={fix}")

    def check_interference(self) -> Dict:
        """Check interferences in the active assembly."""
        doc = self._require_doc()
        if doc.GetType() != SW_DOC_ASSEMBLY:
            raise DrawingError("Interference check requires an assembly.")

        interference = doc.InterferenceDetection
        interference.UseTransform = True
        interference.TreatCoincidenceAsInterference = False
        interference.IncludeSurfaceBodies = True
        count = interference.GetCount()
        results = []
        for i in range(count):
            interf = interference.Interference(i)
            results.append({
                "volume_mm3": interf.Volume / 1000.0 if interf.Volume else 0,
            })
        interference.Done()
        self._log("INFO", f"Interference check: {count} found")
        return {"count": count, "interferences": results}

    def list_components(self) -> List[Dict[str, str]]:
        """List all components in the assembly."""
        doc = self._require_doc()
        components = []
        comp = doc.GetFirstComponent2()
        while comp:
            components.append({"name": comp.Name2, "path": comp.GetPathName()})
            comp = comp.GetNext()
        return components

    # ═══════════════════════════════════════════════════════════
    #  DRAWING OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def add_drawing_view(self, view_type: str = "front",
                         x: float = 0.1, y: float = 0.15,
                         scale: float = 1.0,
                         model_path: Optional[str] = None):
        """Add a drawing view."""
        types = {
            "front": 1, "back": 2, "left": 3, "right": 4,
            "top": 5, "bottom": 6, "isometric": 7,
            "trimetric": 8, "dimetric": 9,
        }
        vt = types.get(view_type.lower(), 1)
        doc = self._require_doc()
        view = doc.CreateDrawViewFromModelView3(
            model_path or doc.GetPathName(),
            str(vt), _m(x), _m(y), scale,
        )
        if view is None:
            raise DrawingError("Failed to create drawing view.")
        self._log("INFO", f"Drawing view: {view_type}")
        return view

    def add_annotation(self, text: str, x: float = 0.05, y: float = 0.05):
        """Add a text annotation to the active drawing."""
        doc = self._require_doc()
        note = doc.AddNote(text, _m(x), _m(y))
        self._log("DEBUG", f"Annotation: '{text[:20]}...'")
        return note

    # ═══════════════════════════════════════════════════════════
    #  MEASUREMENT & PROPERTIES
    # ═══════════════════════════════════════════════════════════

    def get_mass_properties(self) -> Dict[str, float]:
        """Get mass properties of the active part."""
        doc = self._require_doc()
        try:
            mp = doc.Extension.CreateMassProperty()
            return {
                "mass": mp.Mass,
                "volume": mp.Volume,
                "surface_area": mp.SurfaceArea,
                "density": mp.Density,
                "center_x": mp.CenterOfMassX,
                "center_y": mp.CenterOfMassY,
                "center_z": mp.CenterOfMassZ,
            }
        except Exception as e:
            self._log("WARN", f"Mass properties failed: {e}")
            return {}

    def get_bounding_box(self) -> Optional[Dict[str, float]]:
        """Get bounding box of the active part."""
        doc = self._require_doc()
        try:
            box = doc.GetBox(0)  # 0 = extents, returns [x1,y1,z1,x2,y2,z2]
            return {
                "min_x": _mm(box[0]), "min_y": _mm(box[1]), "min_z": _mm(box[2]),
                "max_x": _mm(box[3]), "max_y": _mm(box[4]), "max_z": _mm(box[5]),
                "width": _mm(box[3] - box[0]),
                "depth": _mm(box[4] - box[1]),
                "height": _mm(box[5] - box[2]),
            }
        except Exception as e:
            self._log("WARN", f"Bounding box failed: {e}")
            return None

    def measure_distance(self, entity1: str, entity2: str) -> Optional[float]:
        """Measure minimum distance between two entities by name."""
        doc = self._require_doc()
        doc.ClearSelection2(True)
        doc.Extension.SelectByID2(
            entity1, "FACE", 0, 0, 0, False, 0, self._null_callout(), 0,
        )
        doc.Extension.SelectByID2(
            entity2, "FACE", 0, 0, 0, True, 0, self._null_callout(), 0,
        )
        try:
            dist = doc.FeatureManager.GetDistance()
            return _mm(dist)
        except Exception as e:
            self._log("WARN", f"Measure failed: {e}")
            return None

    # ═══════════════════════════════════════════════════════════
    #  CONFIGURATIONS & EQUATIONS
    # ═══════════════════════════════════════════════════════════

    def list_configurations(self) -> List[str]:
        doc = self._require_doc()
        configs = doc.GetConfigurationNames()
        return list(configs)

    def activate_configuration(self, config_name: str):
        doc = self._require_doc()
        doc.ShowConfiguration2(config_name)
        self._log("INFO", f"Activated configuration: {config_name}")

    def get_equations(self) -> List[Dict[str, str]]:
        doc = self._require_doc()
        eqs = doc.GetEquations()
        return [{"equation": eq} for eq in eqs]

    def add_equation(self, equation: str):
        doc = self._require_doc()
        doc.AddEquation(equation)
        self._log("INFO", f"Equation: {equation}")

    # ═══════════════════════════════════════════════════════════
    #  SELECTION
    # ═══════════════════════════════════════════════════════════

    def select_by_id(self, name: str, object_type: str = "FACE"):
        """Select an object by name and type."""
        doc = self._require_doc()
        doc.Extension.SelectByID2(
            name, object_type, 0, 0, 0, False, 0, self._null_callout(), 0,
        )

    def clear_selection(self):
        self._require_doc().ClearSelection2(True)

    # ═══════════════════════════════════════════════════════════
    #  UTILITY
    # ═══════════════════════════════════════════════════════════

    def send_command(self, command: str):
        self._com_obj.RunCommand(
            self._com_obj.CommandManager.GetCommandID(command), ""
        )

    def get_version(self) -> str:
        try:
            return self._com_obj.RevisionNumber
        except Exception:
            return "Unknown"

    def rebuild(self):
        """Rebuild the active model."""
        self._require_doc().ForceRebuild3(False)
        self._log("DEBUG", "Model rebuilt")

    def zoom_to_fit(self):
        """Fit the view to the model."""
        try:
            self._com_obj.ActiveDoc.ActiveView.FitView()
        except Exception as e:
            self._log("WARN", f"Zoom to fit failed: {e}")

    def set_view_orientation(self, view_name: str = "Isometric"):
        """Set the view orientation."""
        try:
            view_map = {
                "front": 1, "back": 2, "left": 3, "right": 4,
                "top": 5, "bottom": 6, "isometric": 7,
            }
            vt = view_map.get(view_name.lower(), 7)
            self._com_obj.ActiveDoc.ActiveView.SetViewDisplayMode(vt)
        except Exception as e:
            self._log("WARN", f"Set view failed: {e}")

    def capture_screenshot(self, output_path: Optional[str] = None,
                           width: int = 1920, height: int = 1080) -> Optional[str]:
        """Capture a screenshot of the active viewport."""
        try:
            if output_path is None:
                import tempfile
                output_path = os.path.join(tempfile.gettempdir(), "sw_screenshot.png")
            self._com_obj.ActiveDoc.ActiveView.GraphicsRedraw(None)
            self._com_obj.SaveBMPFile(output_path, width, height, 0)
            self._log("INFO", f"Screenshot: {output_path}")
            return output_path
        except Exception as e:
            self._log("WARN", f"Screenshot failed: {e}")
            return None

    def set_display_mode(self, mode: str = "shaded"):
        """Set display mode for the active view."""
        mode_map = {
            "wireframe": 1,
            "hidden_lines_visible": 2,
            "hidden_lines_removed": 3,
            "shaded": 4,
        }
        vt = mode_map.get(mode.lower(), 4)
        try:
            self._com_obj.ActiveDoc.ActiveView.SetDisplayMode(vt)
        except Exception as e:
            self._log("WARN", f"Set display mode failed: {e}")

    # ═══════════════════════════════════════════════════════════
    #  Drawing Primitives (alias for sketch methods)
    # ═══════════════════════════════════════════════════════════

    def draw_line(self, start: Tuple[float, float],
                  end: Tuple[float, float]):
        self.sketch_line(start, end)

    def draw_circle(self, center: Tuple[float, float], radius: float):
        self.sketch_circle(center, radius)

    def draw_rectangle(self, p1: Tuple[float, float],
                       p2: Tuple[float, float]):
        self.sketch_rectangle(p1, p2)

    def draw_text(self, text: str, position: Tuple[float, float],
                  height: float):
        self._sm.CreateText(
            text, _m(position[0]), _m(position[1]), 0.0, _m(height),
        )
