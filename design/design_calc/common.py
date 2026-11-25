"""
设计计算公共工具库

单位转换、材料性能、摩擦系数、安全系数推荐、统一基类
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import math


# ═══════════════════════════════════════════════════════════
#  统一结果基类
# ═══════════════════════════════════════════════════════════

@dataclass
class CalcResult:
    """所有计算结果的基类"""
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def summary(self) -> str:
        """生成摘要文本"""
        lines = []
        for k, v in self.to_dict().items():
            if k in ('warnings', 'notes'):
                continue
            if isinstance(v, float):
                lines.append(f"  {k}: {v:.4g}")
            else:
                lines.append(f"  {k}: {v}")
        
        if self.warnings:
            lines.append("\n  ⚠️  警告:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        
        return "\n".join(lines)
    
    def to_markdown(self, title: str = "计算结果") -> str:
        """生成 Markdown 报告"""
        md = [f"## {title}\n"]
        md.append("| 项目 | 数值 |")
        md.append("|------|------|")
        
        for k, v in self.to_dict().items():
            if k in ('warnings', 'notes'):
                continue
            if isinstance(v, float):
                md.append(f"| {k} | {v:.4g} |")
            else:
                md.append(f"| {k} | {v} |")
        
        if self.warnings:
            md.append("\n### ⚠️  警告")
            for w in self.warnings:
                md.append(f"- {w}")
        
        return "\n".join(md)


# ═══════════════════════════════════════════════════════════
#  单位转换工具
# ═══════════════════════════════════════════════════════════

class UnitConverter:
    """单位转换工具"""
    
    # 长度
    MM_TO_M = 0.001
    M_TO_MM = 1000
    MM_TO_INCH = 0.0393701
    INCH_TO_MM = 25.4
    
    # 力
    N_TO_KGF = 0.101972
    KGF_TO_N = 9.80665
    N_TO_LBF = 0.224809
    LBF_TO_N = 4.44822
    
    # 压力
    PA_TO_MPA = 1e-6
    MPA_TO_PA = 1e6
    PA_TO_BAR = 1e-5
    BAR_TO_PA = 1e5
    BAR_TO_MPA = 0.1
    MPA_TO_BAR = 10
    KPA_TO_MPA = 0.001
    MPA_TO_KPA = 1000
    
    # 功率
    W_TO_KW = 0.001
    KW_TO_W = 1000
    KW_TO_HP = 1.34102
    HP_TO_KW = 0.7457
    
    # 扭矩
    NM_TO_NMM = 1000
    NMM_TO_NM = 0.001
    NM_TO_KGFM = 0.101972
    KGFM_TO_NM = 9.80665
    
    # 温度
    @staticmethod
    def c_to_f(c: float) -> float:
        return c * 9/5 + 32
    
    @staticmethod
    def f_to_c(f: float) -> float:
        return (f - 32) * 5/9
    
    # 速度
    @staticmethod
    def m_min_to_m_s(v_m_min: float) -> float:
        return v_m_min / 60.0
    
    @staticmethod
    def m_s_to_m_min(v_m_s: float) -> float:
        return v_m_s * 60.0
    
    @staticmethod
    def rpm_to_rad_s(rpm: float) -> float:
        return rpm * 2 * math.pi / 60.0
    
    @staticmethod
    def rad_s_to_rpm(rad_s: float) -> float:
        return rad_s * 60.0 / (2 * math.pi)
    
    # 质量
    @staticmethod
    def kg_to_g(kg: float) -> float:
        return kg * 1000
    
    @staticmethod
    def g_to_kg(g: float) -> float:
        return g / 1000


# ═══════════════════════════════════════════════════════════
#  常用材料性能库
# ═══════════════════════════════════════════════════════════

@dataclass
class Material:
    """材料性能数据"""
    name: str
    density: float           # kg/m³
    youngs_modulus: float    # MPa (N/mm²)
    poisson_ratio: float
    yield_strength: float   # MPa
    tensile_strength: float  # MPa
    hardness: str = ""       # 硬度描述


class MaterialLibrary:
    """常用材料性能库"""
    
    MATERIALS: Dict[str, Material] = {
        "6061铝": Material(
            name="6061-T6",
            density=2700,
            youngs_modulus=68900,
            poisson_ratio=0.33,
            yield_strength=276,
            tensile_strength=310,
            hardness="HB95"
        ),
        "7075铝": Material(
            name="7075-T6",
            density=2810,
            youngs_modulus=71700,
            poisson_ratio=0.33,
            yield_strength=503,
            tensile_strength=572,
            hardness="HB150"
        ),
        "45钢": Material(
            name="45#钢",
            density=7850,
            youngs_modulus=209000,
            poisson_ratio=0.269,
            yield_strength=355,
            tensile_strength=600,
            hardness="HB197"
        ),
        "Q235钢": Material(
            name="Q235",
            density=7850,
            youngs_modulus=210000,
            poisson_ratio=0.28,
            yield_strength=235,
            tensile_strength=375,
            hardness="HB120"
        ),
        "304不锈钢": Material(
            name="SUS304",
            density=7930,
            youngs_modulus=193000,
            poisson_ratio=0.29,
            yield_strength=205,
            tensile_strength=520,
            hardness="HB187"
        ),
        "POM": Material(
            name="POM (聚甲醛)",
            density=1410,
            youngs_modulus=2700,
            poisson_ratio=0.35,
            yield_strength=65,
            tensile_strength=70,
            hardness="M79"
        ),
        "ABS": Material(
            name="ABS",
            density=1050,
            youngs_modulus=2300,
            poisson_ratio=0.35,
            yield_strength=40,
            tensile_strength=45,
            hardness="R110"
        ),
    }
    
    @classmethod
    def get(cls, name: str) -> Optional[Material]:
        """获取材料性能"""
        # 模糊匹配
        for key, mat in cls.MATERIALS.items():
            if name.lower() in key.lower() or key.lower() in name.lower():
                return mat
        return None
    
    @classmethod
    def list_materials(cls) -> List[str]:
        """列出所有材料"""
        return list(cls.MATERIALS.keys())


# ═══════════════════════════════════════════════════════════
#  摩擦系数库
# ═══════════════════════════════════════════════════════════

class FrictionCoefficient:
    """常用材料摩擦系数"""
    
    # 静态摩擦系数
    STATIC: Dict[str, float] = {
        "钢-钢 (干)": 0.74,
        "钢-钢 (润滑)": 0.16,
        "钢-铝 (干)": 0.61,
        "钢-铜 (干)": 0.53,
        "铝-铝 (干)": 1.05,
        "钢-POM": 0.35,
        "钢-尼龙": 0.4,
        "钢-PTFE": 0.04,
        "橡胶-钢": 0.9,
        "橡胶-混凝土": 1.0,
    }
    
    # 动态摩擦系数
    DYNAMIC: Dict[str, float] = {
        "钢-钢 (干)": 0.57,
        "钢-钢 (润滑)": 0.06,
        "钢-铝 (干)": 0.47,
        "钢-铜 (干)": 0.36,
        "铝-铝 (干)": 0.8,
        "钢-POM": 0.23,
        "钢-尼龙": 0.3,
        "钢-PTFE": 0.04,
        "橡胶-钢": 0.8,
        "橡胶-混凝土": 0.7,
    }
    
    @classmethod
    def get(cls, pair: str, dynamic: bool = False) -> float:
        """获取摩擦系数"""
        table = cls.DYNAMIC if dynamic else cls.STATIC
        return table.get(pair, 0.3)  # 默认值


# ═══════════════════════════════════════════════════════════
#  安全系数推荐
# ═══════════════════════════════════════════════════════════

@dataclass
class SafetyRecommendation:
    """安全系数推荐"""
    category: str
    description: str
    min_factor: float
    typical_factor: float
    max_factor: float


class SafetyFactors:
    """常用设计安全系数推荐"""
    
    RECOMMENDATIONS: List[SafetyRecommendation] = [
        SafetyRecommendation("静载荷-塑性材料", "静载荷下的塑性材料", 1.25, 1.5, 2.0),
        SafetyRecommendation("静载荷-脆性材料", "静载荷下的脆性材料", 2.0, 3.0, 4.0),
        SafetyRecommendation("动载荷-塑性材料", "交变载荷下的塑性材料", 1.5, 2.0, 2.5),
        SafetyRecommendation("动载荷-脆性材料", "交变载荷下的脆性材料", 3.0, 4.0, 5.0),
        SafetyRecommendation("冲击载荷", "有冲击载荷的场合", 2.5, 3.5, 4.0),
        SafetyRecommendation("可靠性要求高", "人身安全或高可靠性要求", 2.0, 3.0, 4.0),
        SafetyRecommendation("不确定因素多", "载荷/材料/计算不确定", 1.5, 2.0, 3.0),
        SafetyRecommendation("直线导轨", "直线导轨静态安全系数", 3.0, 4.0, 5.0),
        SafetyRecommendation("滚珠丝杆", "滚珠丝杆静态安全系数", 2.0, 3.0, 4.0),
        SafetyRecommendation("轴承", "轴承寿命计算", 1.0, 1.5, 2.0),
        SafetyRecommendation("弹簧", "压缩弹簧切应力安全系数", 1.2, 1.5, 2.0),
        SafetyRecommendation("真空吸盘", "真空吸盘安全系数", 2.0, 3.0, 4.0),
    ]
    
    @classmethod
    def get(cls, category: str) -> Optional[SafetyRecommendation]:
        """获取安全系数推荐"""
        for rec in cls.RECOMMENDATIONS:
            if category.lower() in rec.category.lower():
                return rec
        return None
    
    @classmethod
    def list_categories(cls) -> List[str]:
        """列出所有类别"""
        return [r.category for r in cls.RECOMMENDATIONS]


# ═══════════════════════════════════════════════════════════
#  多方案对比工具
# ═══════════════════════════════════════════════════════════

class SolutionComparator:
    """多方案对比工具"""
    
    @staticmethod
    def compare(results: List[Dict[str, Any]], 
                name_key: str = "name",
                metrics: Optional[List[str]] = None) -> str:
        """
        对比多个方案
        
        Args:
            results: 结果列表，每个是字典
            name_key: 方案名称的键名
            metrics: 要对比的指标列表
        
        Returns:
            Markdown 格式的对比表
        """
        if not results:
            return "无数据"
        
        if metrics is None:
            # 自动获取所有数值键
            all_keys = set()
            for r in results:
                all_keys.update(r.keys())
            metrics = [k for k in all_keys if k != name_key and k not in ('warnings', 'notes')]
        
        md = ["## 方案对比\n"]
        md.append("| 指标 | " + " | ".join([r.get(name_key, f"方案{i+1}") for i, r in enumerate(results)]) + " |")
        md.append("|------|" + "|".join(["------" for _ in results]) + "|")
        
        for m in metrics:
            row = f"| {m} |"
            for r in results:
                val = r.get(m, "-")
                if isinstance(val, float):
                    row += f" {val:.4g} |"
                else:
                    row += f" {val} |"
            md.append(row)
        
        return "\n".join(md)


# ═══════════════════════════════════════════════════════════
#  报告生成器
# ═══════════════════════════════════════════════════════════

class ReportGenerator:
    """设计计算报告生成器"""
    
    @staticmethod
    def generate(title: str, 
                 sections: List[tuple],
                 author: str = "",
                 project: str = "") -> str:
        """
        生成 Markdown 格式的设计计算报告
        
        Args:
            title: 报告标题
            sections: [(section_title, content), ...]
            author: 作者
            project: 项目名称
        
        Returns:
            Markdown 格式报告
        """
        from datetime import datetime
        
        md = [
            f"# {title}\n",
            f"**项目**: {project}  ",
            f"**作者**: {author}  ",
            f"**日期**: {datetime.now().strftime('%Y-%m-%d')}\n",
            "---\n",
        ]
        
        for sec_title, content in sections:
            md.append(f"## {sec_title}\n")
            md.append(content)
            md.append("")
        
        md.append("---")
        md.append("*本报告由设计计算工具自动生成*")
        
        return "\n".join(md)
