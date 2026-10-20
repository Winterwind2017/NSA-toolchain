"""
cad_framework.utils - Utility functions

Coordinate conversion, unit conversion, helpers.
"""

import math
from typing import Tuple, List, Any

# Type aliases
Point2D = Tuple[float, float]
Point3D = Tuple[float, float, float]
Points2D = List[Point2D]
Points3D = List[Point3D]

# Common unit conversions (AutoCAD uses drawing units)
MM_TO_INCH = 1.0 / 25.4
INCH_TO_MM = 25.4
DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi


def mm_to_inch(mm: float) -> float:
    return mm * MM_TO_INCH


def inch_to_mm(inch: float) -> float:
    return inch * INCH_TO_MM


def polar_to_cartesian(radius: float, angle_deg: float, center: Point2D = (0, 0)) -> Point2D:
    """Convert polar coordinates to cartesian"""
    angle_rad = angle_deg * DEG_TO_RAD
    x = center[0] + radius * math.cos(angle_rad)
    y = center[1] + radius * math.sin(angle_rad)
    return (x, y)


def to_variant_array(*points: Point3D):
    """
    Convert Python tuples to a COM-compatible variant array of doubles.
    For AutoCAD/SolidWorks COM API array parameters.
    """
    import pythoncom
    flat = []
    for pt in points:
        flat.extend(pt)
    return win32com_array(flat)


def win32com_array(data: list):
    """Create a win32com-compatible array (single-dimension double array)."""
    try:
        import pythoncom
        return data  # In many cases plain list works
    except ImportError:
        return data
