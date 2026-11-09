"""配合代号判据（`dim.fit_code`）。

判据用**独立表值**核对（GB/T 1800.1 手查值），不是拿实现测实现。
spec 2.3：超范围必须抛错，不许返回近似值。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from ..fit import fit_deviation
from .base import close, verdict

# (代号, 公称尺寸 mm, 上偏差 mm, 下偏差 mm) —— 手查 GB/T 1800.1
REFERENCE: Sequence[Tuple[str, float, float, float]] = (
    ("H7", 50.0, 0.025, 0.0),      # IT7@30–50 = 25 µm，孔 H：EI=0
    ("h6", 50.0, 0.0, -0.016),     # IT6@30–50 = 16 µm，轴 h：es=0
    ("H8", 100.0, 0.054, 0.0),     # IT8@80–120 = 54 µm
    ("f7", 25.0, -0.020, -0.041),  # f@18–30 = -20 µm，IT7 = 21 µm
    ("g6", 10.0, -0.005, -0.014),  # g@6–10 = -5 µm，IT6 = 9 µm
)


def judge_fit_code(rb: Any = None, *,
                   reference: Sequence[Tuple[str, float, float, float]] = REFERENCE,
                   out_of_range: float = 600.0) -> Dict[str, Any]:
    checks: Dict[str, bool] = {}
    rows: List[Dict[str, Any]] = []
    for code, nominal, upper, lower in reference:
        try:
            got_u, got_l = fit_deviation(code, nominal)
        except Exception as exc:                    # noqa: BLE001
            got_u = got_l = None
            rows.append({"code": code, "nominal": nominal, "error": str(exc)})
        rows.append({"code": code, "nominal": nominal,
                     "expected": [upper, lower], "read": [got_u, got_l]})
        checks["fit:%s@%g" % (code, nominal)] = (close(got_u, upper, 1e-9)
                                                 and close(got_l, lower, 1e-9))
    raised = None
    try:
        fit_deviation("H7", out_of_range)
    except Exception as exc:                        # noqa: BLE001
        raised = type(exc).__name__
    checks["out_of_range_raises"] = raised is not None
    bad = None
    try:
        fit_deviation("X7", 50.0)
    except Exception as exc:                        # noqa: BLE001
        bad = type(exc).__name__
    checks["unknown_code_raises"] = bad is not None
    detail = {"reference": rows, "out_of_range_raised": raised,
              "unknown_code_raised": bad}
    return verdict(checks, detail, {"reference": rows})
