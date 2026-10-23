# 往外扩 · 待办清单（按预估用时**降序**）

> 触发口令：用户说「**继续往外扩**」时，从这个表**最上面**开始啃。
> 每条都记录了"为什么它这么久"和"第一步该做什么"，避免重新踩坑。
> 用时基于本项目实测节奏：一次 GUI 探针 3–4 分钟，一条能力平均 3–6 次探针。

| # | 方向 | 预估 | 风险 | 第一步 |
|---|---|---|---|---|
| 1 | **LAD / FBD 导入**（梯形图、功能块图） | **8–16 h** | 高 | 先探"导入一份只有 LAD 程序的 XML 会不会被接受"；很可能撞上自绘编辑器（和编译器原话同一个天花板） |
| 2 | **iQ-R / iQ-F 机型** | **4–8 h** | 中高 | 新建工程对话框里换系列索引，看 `!!Config.xml` 的 `Unit`/`UnitId`；再跑 `project.new` 判据 |
| 3 | **结构体数组 / FB 参数传递** | **3–5 h** | 中 | 数组成员在样例里是 `InstantlyDefinedType/ArrayTypeSpec`；FB 的 `Parameters`（Inout/Input/Output）目前是被删掉的，要重新研究怎么带参数 |
| 4 | **多程序定向写入**（现在只写第一个程序） | **2–3 h** | 中 | 在导航树里选中目标程序再粘贴；或用 XML 导入多程序后逐个 paste |
| 5 | **FX5C 换机型** | **1.5–2.5 h** | 低 | `new_project(series=...)` 换索引 + 判据里的 `Unit=` 期望值 |
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
