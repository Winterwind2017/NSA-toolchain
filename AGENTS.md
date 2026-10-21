# AGENTS.md — 在这个仓库里干活的第一页

## 1. 只发布验证过的能力

`docs/registry.yaml` 是唯一事实来源：`verified` 必须带 `evidence`，
`implemented ⊆ verified`。`src/nxkit/caps.py` 里每条能力都必须"真机跑一遍 +
判据通过"；没打通的写进 `docs/UNSUPPORTED.md`，不要偷偷标成能用。

## 2. 判据用读数，不用返回值

NX 的坑和 AutoCAD 一样：调用返回对象/True 不代表几何变了。所有判据从 NX 里读回
（`MeasureManager` 的体积/面积、`GetBodies()` 数量、特征名、属性值），
不看返回值。

## 3. 跑真机

```bash
python -m nxkit selftest          # 离线（不需要 NX）
python -m nxkit run --only solid  # 真机一族
python -m nxkit run               # 全部，一次会话 ~14 s
```

## 4. 会话与超时

- 一次 `run_journal` 会话约 13 s；**批量能力放在一个 job 里**，不要一条一起进程。
- `session.run` 默认 900 s 超时；超时会 `taskkill /T` 掉 `run_journal` 与 `ugraf`。
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

## 6. 文档与代码一致

`README.md` 的能力计数、`docs/registry.yaml`、`docs/UNSUPPORTED.md` 必须与
`src/nxkit/caps.py` 一致；提交前跑 `python -m nxkit selftest` 与
`python -m pytest tests -q`。
