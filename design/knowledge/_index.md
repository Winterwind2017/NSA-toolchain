# 非标自动化设计知识库 — 索引

> 本知识库从网络公开资料中提取，涵盖力学、机械设计、机构、材料、选型、公差、DFM 七大模块。
> 配套 Python 计算工具库位于 `design/design_calc/`。使用前把 `design/` 放进 `PYTHONPATH`，然后 `from design_calc import motor`。

---

## 知识模块

| # | 模块 | 文件 | 核心内容 | 来源 |
|---|------|------|---------|------|
| 0 | 速查表 | `00-速查表/常用标准件速查.md` | 螺丝/铝型材/气缸/导轨/丝杆/电机/传感器/电磁阀/材料密度/公差 快速参考 | 行业标准汇总 |
| 1 | 力学基础 | `01-力学基础/核心公式.md` | 应力/应变/弯曲/扭转/压杆稳定/应力集中 | Hibbeler《材料力学》 |
| 2 | 机械设计核心 | `02-机械设计核心/失效理论与疲劳.md` | von Mises/Goodman/Soderberg/Gerber/螺栓/焊接 | Shigley《机械设计》 |
| 3 | 机构设计 | `03-机构设计/传动设计.md` | 齿轮/带传动/凸轮/连杆/传动方案速查 | Shigley + Uicker + GB/T 3480 |
| 3b | 传动元件 | `03-机构设计/传动元件选型.md` | 丝杆/同步带/齿条/链条/分割器决策树 | BV13t896UEWL P10 大纲 + 非标实务 |
| 3c | 齿轮 | `03-机构设计/齿轮设计与选型.md` | 失效/材质/选型vs设计/直斜锥蜗/插件出图 | BV13t896UEWL P12 大纲 + GB/T 3480 |
| 4 | 材料与热处理 | `04-材料与热处理/常用材料与处理.md` | 11种材料性能表/热处理工艺/表面处理/选材决策树 | 米思米 + 国标 |
| 5 | 标准件选型 | `05-标准件选型/选型计算.md` | 伺服电机/气缸/丝杆/导轨/轴承完整计算公式 | 鸣志/SMC/THK/HIWIN |
| 5b | 电机种类 | `05-标准件选型/电机种类选型.md` | 异步/步进/伺服/直驱决策树 + 驱动功率 + 步进矩频 | BV13t896UEWL P8 大纲 + 非标实务 |
| 5c | 气动元件 | `05-标准件选型/气动元件选型.md` | 气源链/FRL/气缸种类/无杆/手指/真空/配件 | BV13t896UEWL P9 大纲 + SMC惯例 |
| 5d | 轴承联轴器 | `05-标准件选型/轴承与联轴器选型.md` | 轴承种类/寿命计算/选型速查/联轴器种类/扭矩计算/安装维护 | SKF/NSK + 米思米 |
| 5e | 真空系统 | `05-标准件选型/真空系统设计.md` | 真空发生器/真空泵/吸盘选型/吸力计算/回路设计/特殊工件方案 | SMC/PISCO + 非标实务 |
| 6 | 公差与配合 | `06-公差与配合/GB公差标准.md` | IT公差表/常用配合/尺寸链/GD&T/粗糙度 | GB/T 1800~1804 + 1182 |
| 7 | DFM与失效 | `07-DFM与失效案例/设计避坑指南.md` | 机加/钣金/焊接/装配约束/十大错误/失效模式 | 行业经验总结 |
| 7b | 机械安全 | `07-DFM与失效案例/机械安全设计.md` | 安全设计原则/防护装置/安全控制/电气安全/气动安全/运动安全/人机工程/检查清单 | GB/T 15706 + GB 5226.1 + ISO 13849 |
| 8 | 减速机与传感器 | `08-减速机与传感器/选型指南.md` | 行星/谐波/RV减速机 + 光电/接近/视觉/力/位移传感器 + 气动系统 | 恩坦斯特/基恩士/SMC |
| 8b | 电磁阀 | `08-减速机与传感器/电磁阀选型.md` | 9步选阀/5/2与5/3中位/阀岛/梭阀双压快排/电气与配管 | BV13t896UEWL P11 大纲 + SMC惯例 |
| 9 | 控制工程 | `09-控制工程/伺服调参与PID.md` | 伺服三环控制/增益调试/PID整定/气动回路设计 | 雷赛/安川调试手册 + Ogata |
| 9b | 节拍与时序 | `09-控制工程/节拍与时序图.md` | 动作流程/串并联/完成时间/关键路径CT/时序图画法 | 非标高工实务 + BV13t896UEWL P13 大纲 |
| 10 | FEA与振动 | `10-FEA与振动/结构验证.md` | 静力/模态/谐响应/屈曲分析 + 共振规避 + 阻尼减振 | Cook《FEA》 + Rao《振动》 |
| 11 | 工程图与电气安全 | `11-工程图与电气安全/规范标准.md` | GB图纸规范/标题栏/技术要求 + 电气布线/拖链 + 安全标准/人机工程 | GB/T 4457 + GB 5226.1 |
| 12 | 设计案例 | `12-设计案例/典型案例.md` | 直线模组/气动压装/视觉抓取 完整设计案例 + 通用设计流程模板 | 行业设计经验 |
| 13 | 项目成本与报价 | `13-项目成本与报价/项目成本估算.md` | 成本构成/标准件价格/机加工估算/人工成本/报价模板/成本控制 | 行业经验汇总 |
| 14 | 典型机构设计 | `14-典型机构设计/常用机构设计.md` | 顶升移栽/翻转/夹爪/定位/移载/升降 常用机构设计要点与选型 | 非标设计经验 |
| 15 | 钣金设计 | `15-钣金设计/钣金设计指南.md` | 常用材料/折弯系数/设计规范/常用结构/表面处理 | 钣金设计手册 |
| 16 | 焊件设计 | `16-焊件设计/焊件设计指南.md` | 常用型材/材料/焊缝设计/变形控制/切割清单 | 焊接设计手册 |
| 17 | 模具设计 | `17-模具设计/模具设计指南.md` | 冲压模/注塑模/压铸模/拔模斜度/模具钢 | 模具设计手册 |
| 18 | 仿真分析 | `18-仿真分析/仿真分析入门指南.md` | 静力分析/模态分析/运动仿真/软件对比/常见问题 | ANSYS/SolidWorks Simulation |
| 19 | 项目管理 | `19-项目管理/项目管理指南.md` | 项目流程/工时估算/交期管理/风险评估/成本构成 | 非标项目管理经验 |

## Python 计算工具

### 驱动与传动

| 模块 | 文件 | 功能 |
|------|------|------|
| `motor` | `design_calc/motor.py` | 电机种类推荐、驱动功率、步进选型、伺服惯量/转矩/RMS |
| `reducer` | `design_calc/reducer.py` | 减速机传动比/输出扭矩/惯量折算/类型推荐(行星/谐波/RV) |
| `gearbox_detailed` | `design_calc/gearbox_detailed.py` | 谐波减速机详细选型、行星减速机详细选型 |
| `ballscrew` | `design_calc/ballscrew.py` | 丝杆导程/精度/寿命/临界转速/DN值 |
| `linear_guide` | `design_calc/linear_guide.py` | 直线导轨选型/寿命计算、同步带传动选型 |
| `gear` | `design_calc/gear.py` | 齿形种类、模数初估、几何、弯曲校核、圆周速度 |
| `transmission` | `design_calc/transmission.py` | 直线/旋转传动路线推荐（丝杆/带/齿条/链条/分割器） |
| `couplings` | `design_calc/couplings.py` | 联轴器选型、同步带轮选型、链轮选型 |
| `bearing_chain` | `design_calc/bearing_chain.py` | 轴承寿命计算、链条传动选型、传送带输送计算 |

### 执行与气动

| 模块 | 文件 | 功能 |
|------|------|------|
| `cylinder` | `design_calc/cylinder.py` | 气缸缸径选型、行程选择、横向载荷校核、缓冲选择 |
| `pneumatic` | `design_calc/pneumatic.py` | 执行器种类/FRL、耗气、气管、电磁阀、真空吸盘 |
| `pneumatic_detailed` | `design_calc/pneumatic_detailed.py` | 气缸速度计算、气管管径计算、真空系统计算 |
| `vacuum_detailed` | `design_calc/vacuum_detailed.py` | 真空发生器详细选型、真空罐容积计算 |
| `vacuum_extreme` | `design_calc/vacuum_extreme.py` | 高/超高真空系统设计、真空室壁厚设计 |
| `air_treatment` | `design_calc/air_treatment.py` | FRL三联件选型、继电器选型、疲劳强度校核 |
| `actuators` | `design_calc/actuators.py` | 电动缸选型、液压缸计算、凸轮机构设计、人机工程计算 |

### 力学与结构

| 模块 | 文件 | 功能 |
|------|------|------|
| `strength` | `design_calc/strength.py` | von Mises、弯曲/扭转/组合应力、截面属性、疲劳安全系数 |
| `mechanics` | `design_calc/mechanics.py` | 梁弯曲强度校核、压杆稳定校核、螺栓强度校核、焊缝强度校核 |
| `shaft` | `design_calc/shaft.py` | 轴强度校核(弯扭组合)、平键连接校核 |
| `spring` | `design_calc/spring.py` | 压缩弹簧设计、扭转弹簧设计 |
| `tolerance` | `design_calc/tolerance.py` | IT公差查表、尺寸链极值法/统计法、配合类型判定 |
| `special_materials` | `design_calc/special_materials.py` | 特种材料强度校核、材料选型推荐 |
| `nanomaterials` | `design_calc/nanomaterials.py` | 纳米材料性能查询、纳米复合材料性能估算 |

### 机构与动力学

| 模块 | 文件 | 功能 |
|------|------|------|
| `dynamics` | `design_calc/dynamics.py` | 惯量匹配计算、翻转扭矩计算、提升力计算、减速比优化 |
| `robot` | `design_calc/robot.py` | 直角机械手负载计算、传送带计算、凸轮分割器选型 |
| `linkage` | `design_calc/linkage.py` | 四杆机构设计、曲柄滑块机构设计 |

### 液压系统

| 模块 | 文件 | 功能 |
|------|------|------|
| `hydraulic_detailed` | `design_calc/hydraulic_detailed.py` | 液压泵选型、油箱容积计算、润滑方式选择 |
| `hydraulic_servo` | `design_calc/hydraulic_servo.py` | 液压伺服系统设计、伺服阀选型 |
| `ultra_high_pressure` | `design_calc/ultra_high_pressure.py` | 超高压液压系统设计、超高压密封设计 |

### 电气与控制

| 模块 | 文件 | 功能 |
|------|------|------|
| `electrical` | `design_calc/electrical.py` | 电缆选型、断路器选型、PLC IO 点数计算 |
| `power_supply` | `design_calc/power_supply.py` | 开关电源选型、传感器选型、夹爪选型 |

### 其他辅助

| 模块 | 文件 | 功能 |
|------|------|------|
| `cycle_time` | `design_calc/cycle_time.py` | 串联/并联/气缸与伺服动作时间/关键路径节拍/UPH |
| `cost_estimate` | `design_calc/cost_estimate.py` | 成本估算、多方案成本对比 |
| `thermal` | `design_calc/thermal.py` | 轴承温升计算、电机发热计算、散热片计算 |
| `safety_layout` | `design_calc/safety_layout.py` | 密封件选型、安全回路设计、设备布局计算 |
| `common` | `design_calc/common.py` | 单位转换、材料库、摩擦系数、安全系数、报告生成 |

## 使用方式

```python
from design_calc import (
    motor, cylinder, ballscrew, tolerance, strength,
    reducer, pneumatic, cycle_time, transmission, gear,
    linear_guide, bearing_chain
)

# 先定电机种类，再校核
kind = motor.recommend_type(positioning=True, repeatability_mm=0.05, speed_mm_s=400)
print(kind["motor"], kind["reason"])

# 伺服电机选型
result = motor.servo_selection(load_mass=50, lead=10, max_speed=500)
print(f"推荐: {result.recommended_motor}, RMS转矩: {result.rms_torque:.2f} N·m")

# 驱动电机功率（翻转/输送连转）
p = motor.drive_power(torque_nm=147.5, rpm=29, efficiency=0.8, safety=2)
print(f"机械功率 {p['mechanical_kw']} kW, 选 {p['selected_kw']} kW")

# 步进：低速开环
st = motor.stepper_selection(load_mass=2, lead=10, max_speed=80, accel_time=0.2, ratio=1)
print(st["recommended_flange"], st["warnings"])

# 气缸选型
result = cylinder.select_bore(load_force=500, pressure=0.5, speed_class="medium")
print(f"推荐缸径: {result['selected_bore_mm']}mm, 余量: {result['margin_percent']}%")

# 丝杆寿命
life = ballscrew.life_hours(Ca=12000, Fm=2000, fw=1.2, nm=1500)
print(f"寿命: {life['life_hours']}h = {life['life_years_2shift']}年(两班制)")

# 尺寸链
chain = tolerance.tolerance_chain_extreme([
    {"nominal": 50, "upper": 0.02, "lower": 0, "type": "inc"},
    {"nominal": 30, "upper": 0.01, "lower": -0.01, "type": "dec"},
])
print(f"封闭环: {chain['nominal']} +{chain['upper']}/{chain['lower']}")

# 疲劳安全系数
n = strength.goodman_safety(sa=80, sm=50, Se=200, Sut=600)
print(f"Goodman 安全系数: {n:.2f}")

# 减速机选型
ratio = reducer.select_ratio(3000, 300)  # i=10
required_t = reducer.output_torque(1.27, 10, efficiency=0.96, ka=1.3)
print(f"所需减速机扭矩: {required_t:.1f} N·m")
rec_type = reducer.recommend_type(load_kg=5, precision_arcmin=3)
print(f"推荐: {rec_type}")

# 气动执行器种类
act = pneumatic.recommend_actuator("linear", stroke_mm=600, lateral_load=True)
print(act["actuator"], act["reason"])
frl = pneumatic.recommend_frl(precision_valve=True)
print(frl["filter"], frl["lubricator"])

# 气动耗气量
q = pneumatic.air_consumption(bore_mm=63, stroke_mm=100, pressure_mpa=0.5, cycles_per_min=30)
print(f"耗气量: {q['consumption_L_min_ANR']} L/min")

# 真空吸盘校核
vac = pneumatic.vacuum_cup_check(cup_diameter_mm=20, vacuum_kpa=60, load_kg=0.5, cups=4)
print(f"吸盘安全系数: {vac['actual_safety_factor']}, {'OK' if vac['pass'] else 'NG'}")

# 节拍：夹紧与定位并联，再加喷码工艺时间
path = cycle_time.from_steps([
    {"name": "挡停", "time": 0.2},
    {"name": "夹紧", "time": 0.25, "group": "hold"},
    {"name": "定位", "time": 0.18, "group": "hold"},
    {"name": "喷码", "time": 0.4},
    {"name": "放行", "time": 0.2},
])
ct = cycle_time.cycle_time(path["critical_path_s"], reset_s=0.15, margin=1.2)
print(f"CT={ct['cycle_time_s']}s, UPH={ct['uph_single']}")

# 电磁阀：垂直缸要中停且不能手推
v = pneumatic.valve_select(action="double", need_mid_stop=True, vertical_load=True, valve_count=8)
print(v["valve"], v["manifold"], v["notes"])

# 传动路线：2m 行程、1.2m/s、精度 0.1mm
d = transmission.recommend_drive("linear", stroke_mm=2000, speed_mm_s=1200, repeatability_mm=0.1)
print(d["drive"], d["reason"])

# 齿轮：500W、800rpm、i=2
g = gear.pair_summary(torque_nm=9550*0.5/800, rpm_pinion=800, ratio=2, z1=17)
print(g["module_mm"], g["geometry"]["center_distance_mm"], g["bending"]["pass"])

# 直线导轨选型
guide = linear_guide.linear_guide_selection(horizontal_load=10, vertical_load=50, stroke_length=500)
print(f"推荐导轨: {guide.recommended_size}, 寿命: {guide.life_hours:.0f}小时")

# 同步带选型
belt = linear_guide.timing_belt_selection(motor_speed_rpm=3000, output_speed_rpm=1000, power_kw=0.5)
print(f"推荐带型: {belt.belt_pitch}, 带宽: {belt.required_width:.1f}mm")

# 压缩弹簧设计
spring = linear_guide.compression_spring_design(required_force=50, required_deflection=20)
print(f"线径: {spring.wire_diameter:.1f}mm, 刚度: {spring.spring_rate:.2f}N/mm")

# 真空吸盘选型
vac_cup = linear_guide.vacuum_cup_selection(payload_kg=5, number_of_cups=2)
print(f"推荐吸盘: {vac_cup.recommended_size}, 安全系数: {vac_cup.safety_factor:.2f}")

# 轴承寿命计算
bearing = bearing_chain.bearing_life_calculation(radial_load=2.0, speed_rpm=1500)
print(f"推荐轴承: {bearing.recommended_type}, L10寿命: {bearing.life_L10_hours:.0f}小时")

# 链条传动选型
chain = bearing_chain.chain_drive_selection(motor_speed_rpm=1500, output_speed_rpm=500, power_kw=1.5)
print(f"推荐链条: {chain.chain_pitch}, 链速: {chain.chain_speed_m_s:.2f}m/s")

# 传送带计算
conveyor = bearing_chain.conveyor_calculation(material_weight_kg=2, conveyor_length=1.5)
print(f"所需电机: {conveyor.required_motor_kw:.3f}kW, 节拍: {conveyor.cycle_time_s:.1f}s/件")

# ==================== 新增工具示例 ====================

# 联轴器选型
from design_calc import couplings
result = couplings.coupling_selection(motor_torque_nm=1.27, motor_shaft_dia=14, load_shaft_dia=12)
print(f"推荐联轴器: {result.recommended_type} {result.recommended_size}")

# 惯量匹配计算
from design_calc import dynamics
result = dynamics.inertia_matching(load_inertia_kg_m2=0.001, motor_inertia_kg_m2=0.000008)
print(f"惯量比: {result.inertia_ratio:.1f}, 匹配: {'OK' if result.match_ok else 'NG'}")

# 梁强度校核
from design_calc import mechanics
result = mechanics.beam_bending_check(load_n=500, span_mm=200, width_mm=20, height_mm=10)
print(f"弯曲应力: {result.max_bending_stress:.1f} MPa, 安全系数: {result.safety_factor:.2f}")

# 轴强度校核
from design_calc import shaft
result = shaft.shaft_strength_check(shaft_dia_mm=20, bending_moment_nmm=50000, torque_nmm=30000)
print(f"当量应力: {result.equivalent_stress:.1f} MPa, 安全系数: {result.safety_factor:.2f}")

# 电缆选型
from design_calc import electrical
result = electrical.cable_selection(power_kw=1.5, voltage_v=220, length_m=10)
print(f"推荐电缆: {result.cable_type}, 电压降: {result.voltage_drop_v:.2f} V")

# 开关电源选型
from design_calc import power_supply
result = power_supply.power_supply_selection(devices={"传感器": 0.5, "电磁阀": 1.0, "PLC": 0.3})
print(f"推荐电源: {result.recommended_model}, 总功率: {result.total_power_w:.1f} W")

# 成本估算
from design_calc import cost_estimate
result = cost_estimate.CostEstimator.estimate_from_selection(
    selections={"servo_400W": 2, "guide_20": 4, "ballscrew_1605": 1},
    assembly_hours=20, design_hours=40
)
print(f"总成本: {result.total_cost:.0f} 元, 报价: {result.selling_price:.0f} 元")

# 特种材料强度校核
from design_calc import special_materials
result = special_materials.special_material_check(material="TC4钛合金", stress_mpa=300)
print(f"屈服强度: {result.yield_strength:.0f} MPa, 安全系数: {result.safety_factor:.2f}")
```
