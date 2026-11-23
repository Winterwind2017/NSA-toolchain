"""把 FEA 结果与可制造性（DFM）合成一个结论。

单看一边都会误导：
* FEA 说"够强"，但件可能做不出来（内角太小、深宽比过大）；
* DFM 说"能做"，但它不管强度。

所以这里只做三件事：把两边的 findings 拼在一起、算出安全系数、
给出一个**保守**结论（`是否可交付`）——只有"做得出来"且"强度够"才是 True。

注意强度是**名义应力**（一维杆/梁公式），不是 FEA 的峰值应力；
真实峰值会出现在孔边/端部（应力集中），这里用 `concentration` 系数显式说明，
不假装它是精确值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..dfm.rules import Finding, Report
from .mesh import FeaError


@dataclass
class Combined:
    verdict: str                       # pass / weak / unmakable / both / no_result
    makeable: bool
    strong_enough: bool
    safety_factor: float
    stress_nominal: float
    stress_peak: float                 # = nominal × concentration
    displacement: float
    deflection_limit: Optional[float]
    dfm: List[Finding] = field(default_factory=list)
    fea: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "pass"

    def to_dict(self) -> dict:
        return {"verdict": self.verdict, "makeable": self.makeable,
                "strong_enough": self.strong_enough,
                "safety_factor": self.safety_factor,
                "stress_nominal": self.stress_nominal,
                "stress_peak": self.stress_peak,
                "displacement": self.displacement,
                "deflection_limit": self.deflection_limit,
                "dfm": [f.to_dict() for f in self.dfm],
                "fea": [f.to_dict() for f in self.fea]}

    def to_text(self) -> str:
        lines = ["结论：%s" % self.verdict,
                 "  强度：σ_nom=%.1f MPa，σ_peak=%.1f MPa（含集中系数），安全系数 %.2f"
                 % (self.stress_nominal, self.stress_peak, self.safety_factor),
                 "  变形：%.6g mm%s" % (self.displacement,
                                       "" if self.deflection_limit is None
                                       else "（许用 %.6g）" % self.deflection_limit),
                 "  可制造：%s" % ("是" if self.makeable else "否")]
        for f in self.dfm:
            lines.append("    [DFM %s] %s → %s" % (f.severity, f.detail, f.fix))
        for f in self.fea:
            lines.append("    [FEA %s] %s → %s" % (f.severity, f.detail, f.fix))
        return "\n".join(lines)


def combine(fea_out: Dict[str, object], *, sigma_allow: float,
            dfm: Optional[Report] = None,
            deflection_limit: Optional[float] = None,
            concentration: float = 3.0,
            min_safety: float = 1.5) -> Combined:
    """合成结论。

    * sigma_allow：材料许用应力（MPa）；
    * concentration：名义→峰值的集中系数（孔边/端部，默认 3.0，可按结构覆盖）；
    * min_safety：要求的最小安全系数（默认 1.5）；
    * deflection_limit：许用挠度（mm），给了就一并判。
    """
    if fea_out.get("stage") != "done":
        raise FeaError("FEA 没解出来，无法合成结论：%s" % (fea_out.get("run") or {}))
    sigma_allow = float(sigma_allow)
    if not (sigma_allow > 0):
        raise FeaError("许用应力必须为正")
    nominal = float(fea_out.get("stress_nominal") or 0.0)
    if nominal <= 0:
        raise FeaError("FEA 结果里没有 stress_nominal，无法判强度")
    peak = nominal * float(concentration)
    sf = sigma_allow / peak if peak > 0 else float("inf")
    disp = abs(float(fea_out.get("measured") or 0.0))

    strong = sf >= min_safety
    fea_findings: List[Finding] = []
    if not strong:
        fea_findings.append(Finding(
            "strength_insufficient", "error", "强度",
            "σ_peak=%.1f MPa，安全系数 %.2f < %.2f" % (peak, sf, min_safety),
            "加大截面/换更高强度材料/降低载荷"))
    if deflection_limit is not None and disp > deflection_limit:
        fea_findings.append(Finding(
            "deflection_exceeded", "error", "变形",
            "挠度 %.6g mm > 许用 %.6g mm" % (disp, deflection_limit),
            "提高截面惯性矩（加厚/加高），或缩短跨距"))
        strong = False

    dfm_findings = list(dfm.findings) if dfm else []
    makeable = not any(f.severity == "error" for f in dfm_findings)

    if not makeable and not strong:
        verdict = "both"
    elif not makeable:
        verdict = "unmakable"
    elif not strong:
        verdict = "weak"
    else:
        verdict = "pass"

    return Combined(verdict=verdict, makeable=makeable, strong_enough=strong,
                    safety_factor=sf, stress_nominal=nominal, stress_peak=peak,
                    displacement=disp, deflection_limit=deflection_limit,
                    dfm=dfm_findings, fea=fea_findings)


def to_report(c: Combined) -> Report:
    """转成 DFM 的 Report，方便和可制造性报告并排打印。"""
    rep = Report("fea+dfm")
    rep.findings.extend(c.fea)
    rep.findings.extend(c.dfm)
    if c.verdict == "pass" and not rep.findings:
        return rep
    if c.verdict != "pass" and not any(f.severity == "error" for f in rep.findings):
        rep.findings.append(Finding(
            "overall_not_pass", "error", "综合结论",
            "结论 %s（可制造=%s，强度够=%s）" % (c.verdict, c.makeable, c.strong_enough),
            "见上面各条"))
    return rep
