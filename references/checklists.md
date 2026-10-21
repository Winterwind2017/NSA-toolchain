# 交付前检查清单

> NX 自动化的失败模式是"脚本跑完了、几何/文件不对"。

## 事前

- [ ] `nxkit status` 找到 `run_journal.exe`
- [ ] `nxkit selftest` 通过
- [ ] 目标能力在 `nxkit list` 里；不在就看 `docs/UNSUPPORTED.md`
- [ ] 想清楚判据（实体数？体积？文件头？）
- [ ] 导出目录里上一次的产物先删掉

## 事中

- [ ] 每步读一次数量/属性，不要等最后
- [ ] 布尔：结果按 `Tag` 去重再量体积
- [ ] 拉伸：`StartExtend/EndExtend.SetValue`，不要碰 `Value`
- [ ] 出图：给 `SelectModelView.SelectedView`，不要设 `Placement`
- [ ] 导出：`session.DexManager`，设 `OutputFile` 后 `Commit`

## 验收

- [ ] 至少一个可复现数字（实体数/面数/体积/面积/文件字节）
- [ ] 存盘重开（L4）后读数仍一致
- [ ] 文件：大小下限 + 文件头（STEP `ISO-10303-21`、IGES `S` 记录）
- [ ] 负面对照跑过一次（错参数 → 判据必须失败）
- [ ] 交付说明写数字与位置，不写"已生成"
