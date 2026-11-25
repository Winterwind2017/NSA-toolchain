"""
成本估算集成

选型后自动估算成本，多方案成本对比。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CostItem:
    """成本项"""
    name: str
    category: str
    unit_price: float
    quantity: int = 1
    total_price: float = 0.0
    brand: str = ""
    remark: str = ""
    
    def __post_init__(self):
        self.total_price = self.unit_price * self.quantity


@dataclass
class CostEstimate:
    """成本估算结果"""
    items: List[CostItem] = field(default_factory=list)
    total_standard: float = 0.0         # 标准件成本
    total_machining: float = 0.0       # 机加工成本
    total_assembly: float = 0.0         # 装配成本
    total_electrical: float = 0.0       # 电气成本
    total_design: float = 0.0           # 设计成本
    total_cost: float = 0.0             # 总成本
    profit_margin: float = 0.15         # 利润率
    selling_price: float = 0.0          # 报价
    warnings: List[str] = field(default_factory=list)


class CostEstimator:
    """成本估算器"""
    
    # 标准件参考价格 (2025年)
    STANDARD_PRICES = {
        # 电机
        "servo_100W": 2000,
        "servo_200W": 3000,
        "servo_400W": 4000,
        "servo_750W": 5500,
        "stepper_57": 800,
        "stepper_86": 1500,
        
        # 气动
        "cylinder_32": 200,
        "cylinder_40": 300,
        "cylinder_50": 400,
        "cylinder_63": 600,
        "vacuum_cup": 50,
        "vacuum_generator": 300,
        
        # 传动
        "guide_15": 80,
        "guide_20": 120,
        "guide_25": 180,
        "ballscrew_1605": 500,
        "ballscrew_2005": 800,
        "coupling": 150,
        "timing_belt": 100,
        
        # 电气
        "plc_small": 1500,
        "plc_medium": 5000,
        "hmi_7": 1500,
        "hmi_10": 2500,
        "sensor": 100,
    }
    
    @classmethod
    def estimate_from_selection(
        cls,
        selections: Dict[str, int],
        assembly_hours: float = 20,
        design_hours: float = 40,
        electric_hours: float = 10,
        hourly_rate: float = 100,
    ) -> CostEstimate:
        """
        从选型结果估算成本
        
        Args:
            selections: 选型字典 {标准件key: 数量}
            assembly_hours: 装配工时
            design_hours: 设计工时
            electric_hours: 电气工时
            hourly_rate: 工时单价 元/小时
        
        Returns:
            CostEstimate
        """
        result = CostEstimate()
        
        # 标准件成本
        for item_key, qty in selections.items():
            price = cls.STANDARD_PRICES.get(item_key, 100)
            item = CostItem(
                name=item_key,
                category="标准件",
                unit_price=price,
                quantity=qty,
            )
            result.items.append(item)
            result.total_standard += item.total_price
        
        # 机加工成本 (估算: 标准件的30%)
        result.total_machining = result.total_standard * 0.3
        
        # 装配成本
        result.total_assembly = assembly_hours * hourly_rate
        
        # 设计成本
        result.total_design = design_hours * hourly_rate
        
        # 电气成本
        result.total_electrical = electric_hours * hourly_rate
        
        # 总成本
        result.total_cost = (
            result.total_standard +
            result.total_machining +
            result.total_assembly +
            result.total_design +
            result.total_electrical
        )
        
        # 报价 (加利润 + 税)
        result.selling_price = result.total_cost * (1 + result.profit_margin) * 1.13
        
        return result


@dataclass
class SolutionCostCompare:
    """多方案成本对比"""
    solution_name: str
    total_cost: float
    selling_price: float
    delivery_time_days: int
    quality_score: float
    score: float = 0.0


class SolutionCostComparator:
    """多方案成本对比"""
    
    @staticmethod
    def compare(
        solutions: List[SolutionCostCompare],
        weight_cost: float = 0.5,
        weight_delivery: float = 0.2,
        weight_quality: float = 0.3,
    ) -> List[SolutionCostCompare]:
        """
        多方案综合评分对比
        
        Args:
            solutions: 方案列表
            weight_cost: 成本权重
            weight_delivery: 交期权重
            weight_quality: 质量权重
        
        Returns:
            按综合得分排序的方案列表
        """
        if not solutions:
            return []
        
        # 归一化
        max_cost = max(s.total_cost for s in solutions)
        max_delivery = max(s.delivery_time_days for s in solutions)
        max_quality = max(s.quality_score for s in solutions)
        
        for s in solutions:
            # 成本越低越好
            cost_score = 1 - s.total_cost / max_cost
            # 交期越短越好
            delivery_score = 1 - s.delivery_time_days / max_delivery
            # 质量越高越好
            quality_score = s.quality_score / max_quality
            
            # 综合得分
            s.score = (
                cost_score * weight_cost +
                delivery_score * weight_delivery +
                quality_score * weight_quality
            ) * 100
        
        # 按得分排序
        solutions.sort(key=lambda x: x.score, reverse=True)
        
        return solutions
