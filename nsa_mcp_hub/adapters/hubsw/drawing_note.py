"""把检验尺寸落到**工程图**上：格式化注释 + 插入注释 + 读回。

之前检验尺寸只是"算出来放在 reads 里"，工程师还得手抄到图上。这里把它变成
一条可验证的动作：

1. 用 ``gear_inspection`` / ``spline`` 算出的报告生成多行注释文本；
2. 插到当前工程图（没有就新建一张），位置可给；
3. **读回**注释文本与位置——判据是"文本里真的出现了 W/M 的数值"，
   而不是"调用没报错"。

为什么不用尺寸标注：公法线/跨棒距是**检验量**，图上通常以技术要求或检验表
的形式给出（不是几何尺寸），注释比尺寸更贴近实际出图习惯。
"""

from __future__ import annotations

import glob
import os
from typing import Any

from .contracts import ContractError

#: swUserPreferenceStringValue_e.swDefaultTemplateDrawing
_TEMPLATE_DRAWING = 10


def _val(obj: Any, name: str) -> Any:
    """属性/方法双形态（SolidWorks COM 常见）。"""
    try:
        value = getattr(obj, name)
    except Exception:                                    # noqa: BLE001
        return None
    if not callable(value):
        return value
    try:
        return value()
    except Exception:                                    # noqa: BLE001
        return value


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        return ("%." + str(digits) + "f") % float(value)
    except (TypeError, ValueError):
        return str(value)


def gear_note_lines(report: dict) -> list[str]:
    """外齿/内齿/斜齿共用的注释行。"""
    kind = report.get("kind", "")
    lines: list[str] = []

    if kind == "helical_involute_gear":
        span = report["normal_span_measurement"]
        balls = report["span_over_balls"]
        lines += [
            "斜齿圆柱齿轮检验（法向）",
            "m_n = %s   z = %d   β = %s°   α_n = %s°"
            % (_fmt(report["normal_module_mm"], 3), report["tooth_count"],
               _fmt(report["helix_angle_deg"], 2),
               _fmt(report["pressure_angle_normal_deg"], 2)),
            "法向公法线 W%d = %s mm" % (span["k"], _fmt(span["span_length_mm"])),
            "量球直径 d_p = %s mm，跨棒距 M = %s mm"
            % (_fmt(balls["ball_diameter_mm"]), _fmt(balls["span_mm"])),
            "（公法线沿法向量，跨棒距用量球）",
        ]
        return lines

    if kind == "internal_involute_gear":
        balls = report["span_over_pins"]
        lines += [
            "内齿圈检验",
            "m = %s   z = %d   α = %s°"
            % (_fmt(report["module_mm"], 3), report["tooth_count"],
               _fmt(report.get("pressure_angle_deg", 20.0), 2)),
            "分度圆 φ%s   齿顶 φ%s   齿根 φ%s"
            % (_fmt(report["pitch_diameter_mm"]), _fmt(report["tip_diameter_mm"]),
               _fmt(report["root_diameter_mm"])),
            "量柱直径 d_p = %s mm，跨棒距 M = %s mm"
            % (_fmt(balls["pin_diameter_mm"]), _fmt(balls["span_mm"])),
        ]
        return lines

    if kind == "external_involute_gear":
        span = report["span_measurement"]
        pins = report["span_over_pins"]
        lines += [
            "渐开线圆柱齿轮检验",
            "m = %s   z = %d   α = %s°   x = %s"
            % (_fmt(report["module_mm"], 3), report["tooth_count"],
               _fmt(report.get("pressure_angle_deg", 20.0), 2),
               _fmt(report.get("profile_shift_x", 0.0), 3)),
            "分度圆 φ%s   齿顶 φ%s   齿根 φ%s"
            % (_fmt(report["pitch_diameter_mm"]), _fmt(report["tip_diameter_mm"]),
               _fmt(report["root_diameter_mm"])),
            "分度圆齿厚 s = %s mm" % _fmt(report["tooth_thickness_at_pitch_mm"]),
            "公法线 W%d = %s mm" % (span["k"], _fmt(span["span_length_mm"])),
            "量柱直径 d_p = %s mm，跨棒距 M = %s mm"
            % (_fmt(pins["pin_diameter_mm"]), _fmt(pins["span_mm"])),
        ]
        return lines

    raise ContractError("不认识的检验报告类型：%r" % (kind,))


def spline_note_lines(report: dict) -> list[str]:
    span = report["span_over_pins"]
    return [
        "矩形花键检验（%s）" % report.get("standard", "GB/T 1144"),
        "D = %s   d = %s   z = %d   b = %s"
        % (_fmt(report["outer_diameter_mm"]), _fmt(report["inner_diameter_mm"]),
           report["tooth_count"], _fmt(report["key_width_mm"])),
        "齿厚 b = %s mm，齿槽宽 = %s mm"
        % (_fmt(report["tooth_thickness_mm"]), _fmt(report["space_width_at_pitch_mm"])),
        "量柱直径 d_p = %s mm，跨棒距 M = %s mm"
        % (_fmt(span["pin_diameter_mm"]), _fmt(span["span_mm"])),
    ]


def note_text(report: dict) -> str:
    """把报告拼成一段多行注释（SW 注释里用 \\n 换行）。"""
    if report.get("kind") == "rectangular_spline":
        return "\n".join(spline_note_lines(report))
    return "\n".join(gear_note_lines(report))


def required_numbers(report: dict) -> list[str]:
    """判据用：注释里必须出现的数值字符串。"""
    numbers: list[str] = []
    kind = report.get("kind", "")
    if kind == "helical_involute_gear":
        numbers = [_fmt(report["normal_span_measurement"]["span_length_mm"]),
                   _fmt(report["span_over_balls"]["span_mm"]),
                   _fmt(report["span_over_balls"]["ball_diameter_mm"])]
    elif kind == "internal_involute_gear":
        numbers = [_fmt(report["span_over_pins"]["span_mm"]),
                   _fmt(report["span_over_pins"]["pin_diameter_mm"])]
    elif kind == "external_involute_gear":
        numbers = [_fmt(report["span_measurement"]["span_length_mm"]),
                   _fmt(report["span_over_pins"]["span_mm"]),
                   _fmt(report["span_over_pins"]["pin_diameter_mm"])]
    elif kind == "rectangular_spline":
        numbers = [_fmt(report["span_over_pins"]["span_mm"]),
                   _fmt(report["span_over_pins"]["pin_diameter_mm"])]
    return numbers


def find_drawing_template(app: Any) -> str:
    """优先用 SW 自己配的图纸模板，再退回 ProgramData 里的 .drwdot。"""
    try:
        configured = app.GetUserPreferenceStringValue(_TEMPLATE_DRAWING)
        if configured and os.path.isfile(configured):
            return configured
    except Exception:                                    # noqa: BLE001
        pass

    candidates: list[str] = []
    for pattern in ("C:/ProgramData/SolidWorks/**/*.drwdot",
                    "C:/ProgramData/SOLIDWORKS/**/*.drwdot"):
        candidates.extend(glob.glob(pattern, recursive=True))
    if not candidates:
        raise RuntimeError("找不到图纸模板（.drwdot）：请在 SW 里配置默认模板")

    def score(path: str) -> tuple[int, int]:
        name = os.path.basename(path).upper()
        return (1 if "GB" in name or "A3" in name else 0, len(name))

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def ensure_drawing(app: Any, current: Any) -> tuple[Any, bool]:
    """当前是工程图就复用，否则新建一张。返回 (文档, 是否新建)。"""
    try:
        # GetType 在本机是**属性**（返回 int），不是方法
        if current is not None and int(_val(current, "GetType") or 0) == 3:
            return current, False
    except Exception:                                    # noqa: BLE001
        pass
    template = find_drawing_template(app)
    drawing = app.NewDocument(template, 0, 0, 0)
    if drawing is None:
        raise RuntimeError("新建工程图失败（模板：%s）" % template)
    return drawing, True


def insert_note(doc: Any, text: str, x: float = 0.06, y: float = 0.10) -> dict[str, Any]:
    """插入注释并设位置，然后**读回**文本与坐标。"""
    note = doc.InsertNote(text)
    if note is None:
        return {"ok": False, "error": "InsertNote 返回 None（当前文档可能不是工程图）"}

    read_text = _val(note, "GetText")
    position = None
    annotation = _val(note, "GetAnnotation")
    if annotation is not None:
        try:
            annotation.SetPosition2(float(x), float(y), 0.0)
            position = list(_val(annotation, "GetPosition") or [])
        except Exception as exc:                         # noqa: BLE001
            return {"ok": False, "text": read_text,
                    "error": "设置注释位置失败：%s" % exc}
    return {
        "ok": bool(read_text),
        "text": read_text,
        "position": [round(v, 6) for v in position] if position else None,
        "type": int(_val(doc, "GetType") or 0),
    }
