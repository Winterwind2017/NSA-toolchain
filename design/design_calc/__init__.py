"""
design_calc - 非标自动化设计计算工具库

提供伺服电机、气缸、丝杆、导轨、齿轮、公差链等选型计算。
所有公式来源于 Shigley《机械设计》、GB 标准、THK/HIWIN/SMC 选型手册。

把仓库的 design/ 放进 PYTHONPATH 后：

    from design_calc import motor, cylinder, ballscrew, tolerance

    result = motor.servo_selection(
        load_mass=50, lead=10, max_speed=500,
        accel_time=0.1, friction_coeff=0.02
    )
    print(result)
"""

from . import motor
from . import cylinder
from . import ballscrew
from . import tolerance
from . import strength
from . import reducer
from . import pneumatic
from . import cycle_time
from . import transmission
from . import gear
from . import linear_guide
from . import bearing_chain
from . import common
from . import couplings
from . import dynamics
from . import mechanics
from . import pneumatic_detailed
from . import cost_estimate
from . import gearbox_detailed
from . import shaft
from . import electrical
from . import robot
from . import thermal
from . import spring
from . import power_supply
from . import linkage
from . import air_treatment
from . import actuators
from . import vacuum_detailed
from . import hydraulic_detailed
from . import safety_layout
from . import vacuum_extreme
from . import hydraulic_servo
from . import special_materials
from . import ultra_high_pressure
from . import nanomaterials

__all__ = [
    "motor",
    "cylinder",
    "ballscrew",
    "tolerance",
    "strength",
    "reducer",
    "pneumatic",
    "cycle_time",
    "transmission",
    "gear",
    "linear_guide",
    "bearing_chain",
    "common",
    "couplings",
    "dynamics",
    "mechanics",
    "pneumatic_detailed",
    "cost_estimate",
    "gearbox_detailed",
    "shaft",
    "electrical",
    "robot",
    "thermal",
    "spring",
    "power_supply",
    "linkage",
    "air_treatment",
    "actuators",
    "vacuum_detailed",
    "hydraulic_detailed",
    "safety_layout",
    "vacuum_extreme",
    "hydraulic_servo",
    "special_materials",
    "ultra_high_pressure",
    "nanomaterials",
]
