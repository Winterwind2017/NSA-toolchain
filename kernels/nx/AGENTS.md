# AGENTS.md — 在这个仓库里干活的第一页

## 1. 只发布验证过的能力

`docs/registry.yaml` 是唯一事实来源：`verified` 必须带 `evidence`，
`implemented ⊆ verified`。`src/nxkit/caps.py` 里每条能力都必须"真机跑一遍 +
判据通过"；没打通的写进 `docs/UNSUPPORTED.md`，不要偷偷标成能用。

## 2. 判据用读数，不用返回值

NX 的坑和 AutoCAD 一样：调用返回对象/True 不代表几何变了。所有判据从 NX 里读回
（`MeasureManager` 的体积/面积、`GetBodies()` 数量、特征名、属性值），
不看返回值。

**容差按量级给**（`judges._tol`）：≥100 容 0.5（体积/面积）、≥1 容 1e-3、
<1 容 1e-6。早期统一用 0.5 绝对容差，把"视图缩放 0.59 vs 期望 0.5"判通过——
比率类判据等于没有。改判据时先想清楚变量量级。

## 3. 跑真机

```bash
python -m nxkit selftest          # 离线（不需要 NX）
python -m nxkit run --only solid  # 真机一族
python -m nxkit run               # 全部 146 条，一次会话 ~47 s
python -m nxkit licenses          # 本机 SPLM 许可覆盖
python tools/lint_scripts.py      # 一次性脚本先编译体检（见 §7）
```

复现口径见 `docs/VERIFY.md`（干净 clone → 11 测试 → selftest → licenses →
真机 146/146 → 技能校验 → 五处数字一致）。

## 4. 会话与超时

- 一次 `run_journal` 会话约 47 s（能力增多线性变慢；DXF/DWG 的翻译器启动各占 ~17 s）；
  **批量能力放在一个 job 里**，不要一条起一个进程。
- `session.run` 默认 300 s 超时；超时会 `taskkill /T` 掉 `run_journal` 与 `ugraf`。
- `run_journal` 成功时也可能返回退出码 1 —— **以 `result.json` 为准**。

## 5. NX 侧的硬规则（踩过的）

- 实体枚举：`Block`/`Cylinder` 用 `NXOpen.Features.Feature.Null`，
  **布尔**用 `NXOpen.Features.BooleanFeature.Null`，**基础视图**用
  `NXOpen.Drawings.BaseView.Null` —— 传错直接 `TypeError`。
- `BodyCollection` 没有 `len()`/下标/`ToArray()`；要实体就从
  `feature.GetBodies()` 拿，并按 `Tag` 去重（布尔后多个特征指向同一个结果体）。
- 拉伸距离：`ExtrudeBuilder.Limits.StartExtend.SetValue(...)` /
  `EndExtend.SetValue(...)`（`Value` 只读）。
- 截面：`CreateSectionsUsingCurves(curves, loop_option, chain_tol, dist_tol, angle_tol)`
  **5 个参数**。
- 出图：`DrawingSheets.InsertSheet(name, StandardSheetSize.A3, 1, 1,
  ProjectionAngleType.FirstAngle)`；基础视图 `SelectModelView.SelectedView = <ModelView>`。
- 导出：`session.DexManager.CreateStepCreator()` / `CreateIgesCreator()`，
  设 `OutputFile` 后 `Commit()`。
- `SaveAs` 目标已存在会抛 `File already exists`，先删。
- 重开用 `parts.OpenActiveDisplay(path, DisplayPartOption.AllowAdditional)`，
  返回值是 tuple（取 `[0]`）。
- 危险接口（**别调**）：`CreateDxfdwgCreator().Commit()` 在 journal 里是空操作（不设
  `SettingsFile` 时还会死循环），DXF/DWG 请走 `NXBIN\dxfdwg.exe` CLI；
  `ComponentPositioner.EstablishNetwork()` 直接崩 journal 会话。
- **只读属性不等于只读**：`BridgeCurveBuilder.StartObject` / `IntersectionCurveBuilder.FirstFace` /
  `SectionViewBuilder.ParentView` 这些属性本身不可赋值，但 `SelectObject`/`ScCollector`
  包着的对象可写（`.Value` / `.AddRules`）。遇到 `property not writable` 先看 `type(prop).__name__`。
- 移动实体只有 `Motion.Option = Distance`（`DistanceVector` + `DistanceValue`）会真的动；
  `DeltaXyz` 模式 Commit 成功但几何不动。
- 选择集三种形态要分清：`SelectObject`（`.Value = obj`）、
  `SelectObjectList`（`.Add([obj])`）、`ScCollector`（`.AddRules([rule])`）；
  传错就是 `No overload matches` 或 `NoneType has no attribute`。
- 部分 builder 的参数是**服务 builder 或裸 float**：`MoveBody.Motion.DeltaX` 是 float、
  `BaseViewBuilder.Scale.Numerator/Denominator` 是 float 且相对自动缩放、
  `ThickenBuilder.FirstOffset` 是 Expression（默认 2.5）。

## 5.1 组合能力比单条更值钱

已验证的"曲线→实体"链路：螺旋线（`curve.helix`）可以当管路径
（`CreateRuleCurveDumb([helix])` + `TubeBuilder.PathSection.AddToSection`）做出弹簧；
拉伸/旋转同样吃曲线截面。往这个方向扩，比硬啃交互式 builder 划算。

## 6. 文档与代码一致

`README.md` 的能力计数、`docs/registry.yaml`、`docs/UNSUPPORTED.md` 必须与
`src/nxkit/caps.py` 一致；提交前跑 `python -m nxkit selftest` 与
`python -m pytest tests -q`。

## 7. 写一次性脚本前先 lint

生成文档、批量探针这类一次性脚本（仓库根的 `_*.py`）在 2026-10-22 一天内
**五次**因为"中文字符串里用了 ASCII 引号"而 SyntaxError，脚本没跑、文档没更新，
几十分钟后才发现。现在有工具兜底：

```bash
python tools/lint_scripts.py            # 编译仓库根 _*.py + tools/*.py
python tools/lint_scripts.py --all      # 再加上 tests/ 与 src/
python tools/lint_scripts.py x.py       # 单个文件
```

失败时会指出行号，并在「中文 + ASCII 引号」这种形态上直接给出提示（改用「」）。
新增/修改一次性脚本后、执行前先过一遍这个工具。

