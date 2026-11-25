---
name: nsa-toolchain
description: >
  NSA-toolchain 的**路由技能**：当用户要做工业自动化/机械设计相关的机器操作
  （AutoCAD 二维三维与出图、SolidWorks 建模装配、UG NX 建模制图、三菱 GX Works3、
  汇川 AutoShop、CODESYS PLC、以及 HAP/笔记库等），但不确定该用哪套工具、
  或任务跨多个软件时，先用这个技能决定"加载哪个域技能、按什么顺序做、
  失败怎么判"。它自己不执行任何操作，只做分诊与门禁。
  Use when a request spans multiple automation domains, when it is unclear which
  kit/skill applies, or before any real-machine automation run that needs a
  readiness check and a pass/fail criterion.
---

# NSA-toolchain（路由）

> 本技能**不执行**。它只回答三件事：**用哪个**、**什么顺序**、**怎么算做成**。
> 真正的配方、判据、坑，在对应域技能里。

## 第一步：定域（一次只加载一个域技能）

| 用户要的事 | 加载这个技能 | 执行内核 | 引擎 |
|---|---|---|---|
| 非标设备/零件/工装/夹具：需求、机构方案、气缸电机丝杆导轨选型、节拍、公差 | `ww-nsa-design` | `design_calc` | 无，先算再建模 |
| 二维绘图/标注/表格/块/图框/多页 PDF/DXF·DWG 导出、电气图、PLC 图 | `ww-autocad-automation` | `acadkit` | AutoCAD 2025 |
| 零件/装配/钣金/工程图/STEP·STL·PDF 导出 | `ww-solidworks-automation` | `swkit` | SolidWorks 2025 |
| 建模/布尔/装配/制图/STEP·IGES 导出 | `ww-nx-automation` | `nxkit` | UG NX 2512 |
| FX5U/SFC/FBD 工程、ST 编程、编译诊断、`.gx3` | `ww-gxworks-automation` | `gxkit` | GX Works3 |
| 汇川 `.hcp`、H3U 指令表、离线下载 | `ww-autoshop-automation` | `autoshopkit` | AutoShop 4.11 |
| CODESYS 3.5 工程/POU/任务/库/归档 | `ww-codesys-automation` | `codesyskit` | CODESYS 3.5 |

判断口径：**看用户要动哪个软件**，不是看要产出什么格式。
`出图` 既可能是 AutoCAD 也可能是 SW 工程图——问一句"图从哪个模型出"比猜便宜。

## 第二步：跨域任务按这个顺序

1. **需求/方案/选型**（先文字和计算，不碰软件）：加载 `ww-nsa-design`，把节拍、力和标准件算完并确认；
2. **结构建模**（SW 或 NX）：先出几何，再谈出图；
3. **二维表达**（AutoCAD 或 SW 工程图）：标注、明细、图框；
4. **导出与自检**：DWG/DXF/PDF/STEP，跑一次往返或差异比对；
5. **控制侧**（GX / AutoShop / CODESYS）：独立于机械，别混在一个上下文里判。

跨域时**一次只开一个引擎**：真机程序（acad.exe/swx.exe 等）抢焦点、抢 COM，
并行跑最容易出"调用返回成功但图形没变"。

## 第三步：三条跨域铁律

1. **只信 `verified`**：每个域技能的能力表就是白名单。表里没有的，先查注册表；
   `dead` 的别再试（每个域都有一份"别试这些"）。
2. **先想判据再动手**：这次操作应该让**实体数/面积/长度/体积/属性/文件签名**
   中的哪一个变化？说不出来就别调——调了也证明不了成功。
3. **失败先分类**：卡住/被拒/权限/只读/不支持，处理方式完全不同。
   `NSA-toolchain` 收录的内核都有错误分类与建议，别把"RPC 被拒"当成"能力不存在"。

## 开工前的 20 秒健康检查

```text
acadkit status      |  swkit status    |  nxkit status
gxkit status        |  autoshopkit doctor |  codesyskit status
```

看到"附加到已运行实例"再动手；看到多个残留进程（如多个 `acad.exe`）先清理。
长任务放后台任务里跑，并给超时——前台等待会把你自己的会话卡死。

## 什么时候不要用本技能

* 用户只是问**某个 API/命令能不能用** → 直接进对应域技能，不用路由；
* 任务只涉及一个软件 → 直接加载那个域技能即可（本技能只在"不确定/跨域"时值钱）；
* 纯文件格式转换（DXF↔DWG 之外的通用格式）→ 先确认是否已有离线工具，别开真机。
