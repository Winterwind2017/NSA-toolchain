# 往外扩 · 待办清单（按预估用时**降序**）

> 触发口令：用户说「**继续往外扩**」时，从这个表**最上面**开始啃。
> 每条都记录了"为什么它这么久"和"第一步该做什么"，避免重新踩坑。
> 用时基于本项目实测节奏：一次 GUI 探针 3–4 分钟，一条能力平均 3–6 次探针。

| # | 方向 | 预估 | 风险 | 第一步 |
|---|---|---|---|---|
| 1 | ~~**LAD / FBD 导入**~~ **已判定不可行（2026-10-24）** | ~~8–16 h~~ → 0 | — | XML 通道只收 ST 正文；9 次实验全被静默丢弃，IL 也不行（详见 `UNSUPPORTED.md` 与下节）。**若还要做，只剩 GUI 键盘画梯形图这一条路（见下）** |
| 2 | **iQ-R / iQ-F 机型** → **基础已打通（2026-10-24）** | 剩余 1–2 h | 低 | 已完成：RCPU/R00 与 FX5S 新建 + ST 往返（3 条能力）。**剩余可选**：r 系列模块配置、iQ-R 的软元件表差异（`inspect.devices` 只验过 FX5U） |
| 3 | **结构体数组 / FB 参数传递** | **3–5 h** | 中 | 数组成员在样例里是 `InstantlyDefinedType/ArrayTypeSpec`；FB 的 `Parameters`（Inout/Input/Output）目前是被删掉的，要重新研究怎么带参数 |
| 4 | **多程序定向写入**（现在只写第一个程序） | **2–3 h** | 中 | 在导航树里选中目标程序再粘贴；或用 XML 导入多程序后逐个 paste |
| 5 | ~~FX5C 换机型~~ → **已做（FX5S）** | 0 | — | 顺带纠正：没有 FX5C 系列，FX5 只有 FX5U/FX5UJ/FX5S；FX5S 已进能力表 |
| 6 | **自给自足模板**（去掉 Sample.xml 依赖） | **0.5–1.5 h** | 中 | 见下：已做到 90%，卡在局部标签 |

## 6 的现状（唯一"已探到底但没解开"的一条）

`templates/base.xml`（我们自己写的骨架）**已经能**导入：
程序、全局标签（BOOL）、全局结构体 + 成员名访问（`datatype.member_access` 用它跑过 0 错）。

**卡住的是局部标签**：同一份骨架下，程序里的 `<Vars>` 局部标签不会进 `LabelData`
（`locals_found=0`），随后 `程序(...)转换中` 报 2 个错。这直接导致
`datatype.import / member_var / custom_members / program.import_fb*` 全都过不了。

已经排除的因素（各花一轮 3 分钟真机验证）：
1. `PouProperties title` 改成样例原文 → 无效
2. `VariableLineNumber` 挪到 AddData 最前 → 无效
3. 去掉 `VariableRemark` 与 `InitialValue` → 无效
4. 给 `MainBody` 补 `BodyProperties`、给 FB 补 `FbPouProperties/FbPouFile/FbFiles` → 有效（FB 那条通了），但局部标签仍不落地

下一步建议：拿一份"样例骨架 + 我们内容"的**可用** XML 与我们骨架生成的 XML，
做**逐元素 diff 后二分**（一次只回退一处差异），定位到底是哪一处让局部标签表不被创建。
按经验 3–5 轮能定位（15–25 分钟）。

## 1 的结论与后续（2026-10-24，投入约 2.5 小时后收口）

**结论：IEC 61131-10 XML 导入只支持 ST 正文。** 证据（同文档 ST 对照每次都成功）：

| 实验 | 结果 |
|---|---|
| 标准 LD（左母线 → 触点 → 线圈 → 右母线） | 静默丢弃 |
| 最小 `<BodyContent xsi:type="LD"><LD/></BodyContent>` | 静默丢弃 |
| `xsi:type="Ladder"` | 静默丢弃 |
| PouProperties 三变体（ST 属性 / 删掉 / LD 属性） | 全丢弃 |
| 属性最小化（去掉 negated/edge/storage） | 静默丢弃 |
| 只放左右母线 | 静默丢弃 |
| XSD 序列顺序（母线在前、元件在后） | 静默丢弃 |
| IL 正文对照 | 静默丢弃 |
| 同文档 ST 正文（对照组） | **程序被创建、0 错** |

旁证：
- `PLCOpenXMLConverter.Impl.dll` 里确实有 `leftPowerRail/contact/coil/...` 与 `LD/Ladder` 字符串，
  说明代码里有 LD 概念，但**导入路径不接**（或需要未公开的开关）。
- DLL 里大量 `Gxw2*` 类名说明那套 LD/FBD 逻辑属于 **GX Works2 工程导入**，不是 IEC XML。
- 无 XSD 随装；官方 Sample.xml 只有 ST；「打开其他格式文件」只有 GX Works2/3/PX/GX Developer；
  「数据操作」无导出入口。

**如果一定要做梯形图**，只剩 GUI 键盘画法：用 F5–F8/F9 那套功能键在自绘画布上摆元件。
评估：**+12–20 h**，且验证困难——梯形图内容读不回 UIA（自绘），
只能靠 `.gx3` 里的步/MIL 反证（`inspect.mil` 已有基础）。这条不建议现在动。
