---
name: ww-nsa-design
description: >
  非标自动化的设计流程和选型计算。用户要设计设备、零件、工装、夹具，或要算气缸、电机、
  伺服、丝杆、导轨、减速机、节拍、公差、强度时先用这个技能。它不打开 CAD。
  算出力和尺寸并经用户确认后，再把建模交给 ww-solidworks-automation 或 ww-nx-automation，
  出图交给对应域技能。Use when the request is to design non-standard automation
  equipment, a part, a fixture, or tooling, or to size a cylinder, motor, ballscrew,
  linear guide, reducer, cycle time, or tolerance stack.
---

# 非标设计（先算后画）

本技能只做设计和计算。几何交给 CAD 域技能，程序交给 PLC 域技能。

| 资料 | 位置 |
|---|---|
| 知识库索引 | `design/knowledge/_index.md` |
| 计算库 | `design/design_calc/` |
| 公式测试 | `design/tests/` |

把 `design/` 放进 `PYTHONPATH` 后：

```python
from design_calc import motor, cylinder, ballscrew, linear_guide, reducer
from design_calc import pneumatic, cycle_time, tolerance, strength, transmission
```

## 七段

每段写完再往下。力和寿命没算完，不建驱动零件。

1. **需求。** 工件（材质、尺寸、重量）、动作、节拍、定位精度、空间、气源和电源。整理成参数表，等用户确认。
2. **方案。** 先读 `design/knowledge/03-机构设计/` 和 `design/knowledge/14-典型机构设计/`。直线、旋转、夹持、输送各选一条，并写明为什么。
3. **选型。** 只调用 `design_calc`，不口算。同一 `group` 的动作用 `cycle_time.from_steps` 取最长，再串联。气缸用 `cylinder.select_bore`，伺服用 `motor.servo_selection`，丝杆用 `ballscrew.life_hours` 和 `critical_speed`，导轨用 `linear_guide.linear_guide_selection`，减速机用 `reducer.recommend_type`，公差用 `tolerance.tolerance_chain_extreme`。电机选定后用 `drive_audit.audit_linear_drive` 复核峰值、RMS、转速、惯量比和抱闸；直齿齿廓坐标用 `gear.involute_xy`，它不生成 SolidWorks 特征。
4. **详细设计。** 尺寸来自上一段的返回值。然后加载 `ww-solidworks-automation` 或 `ww-nx-automation`。
5. **装配。** 干涉检查交给当前 CAD 域技能，分开时应为 0。
6. **出图和 BOM。** 工程图交给 `ww-solidworks-automation` 或 `ww-autocad-automation`。
7. **交付前。** 对照 `design/knowledge/07-DFM与失效案例/` 和 `design/knowledge/11-工程图与电气安全/`。导出的 PDF / STEP 用 `delivery_gate.accept_new_file`，修改时间必须晚于本轮开始，头签名必须对；同一路径重导时哈希必须变过。

## 怎么算做成

- 输入单位写在结果旁边：力是 N，压力是 MPa，导程是 mm，质量是 kg。
- 下面三式里用到的必须能复核：缸径由 `F / (负载率 × 压力)` 算出后再向上取标准缸径；丝杆负载惯量是 `m (lead / 2π)²`，lead 先换成米；节拍是各组取最大后再相加。
- `warnings` 逐条改方案，或写明接受的理由。
- 厂家样本上的额定值优先于这里的初算。这里的结果是方案数，不是最终订货规格。

## 什么时候不用

只问某个 CAD 或 PLC 命令能不能用时，直接进对应域技能。
