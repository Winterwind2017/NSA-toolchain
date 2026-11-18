# AGENTS.md — 给在这台机器/这个仓库里干活的 agent 看的第一页

> 任何 agent 打开这个仓库，先读完这一页，再动手。人类同样适用。

## 0. 挖掘类任务：先出全量清单，再动手

用户明确要求（2026-11-18）：**不要做完一步才建议下一步**。

任何"还能挖什么 / 接下来做什么"的请求，回答顺序必须是：

1. **先给全量清单**：把所有可挖项列全（域 / 门槛 T1–T3 / 影响分 / 工时 / 关键风险），
   并给出**总量**——让人先知道"要到理想效果一共多少东西"；
2. 再给"眼下先做哪几条"（`docs/GAPS.md` 的排序），并说明它只占全量的百分之几；
3. 同时列出**明确不做**的（避免反复讨论已排除的方向）。

清单的机器可读源是 `docs/backlog.yaml`，生成的表是 `docs/BACKLOG.md`
（`python tools/gen_backlog.py`）。加了新想法就写进 backlog.yaml，不要只在对话里说。

> 判据：如果有人只拿到"下一步做 X"而不知道总量，那就是违反了这一条。

## 1. 只发布验证过的东西

`docs/registry.yaml` 是**唯一事实来源**：`verified` 必须带 `evidence`，
`implemented ⊆ verified`。`src/acadkit/caps.py` 里每条能力都必须能
"真机跑一遍 + 判据通过"；没打通的写进 `docs/UNSUPPORTED.md`（按卡在哪里
分类），不要偷偷标成能用。

## 2. 判据用读数，不用返回值

本项目反复踩到"调用返回成功、几何量却不动"：`PlotToFile` 返回 True 但文件
0 字节、`Boolean` 返回 None 却算错体积、`MLeader.TextString` 赋值成功读回空串。
**所有判据都从 AutoCAD 读回**（计数/面积/体积/句柄/文件签名），不看返回值。

## 3. 跑真机套件

```bash
python tests/run_all.py                # 离线 + 真机（约 8–12 分钟）
python tests/run_all.py --skip-live    # 只跑离线（不需要 AutoCAD）
python tests/live_judges.py --only geom,dim   # 只跑某些族
```

单例超过 `--case-timeout`（默认 120 s）会**强杀 acad 并中止**，现场写在
`_scratch/.../TIMEOUT.txt`。真卡死时先看 `_scratch/.../progress.txt` 的
最后一行——它记录到 `build/save/reopen/judge` 哪一步。

## 4. 环境铁律

- 必须 `<<VANILLA>>` 配置启动：`acad.exe /p "<<VANILLA>>"`。直接启动会落到
  `<<ACADE>>`（电气），所有综合开发都要以纯 AutoCAD 为准。
- `CPROFILE` 是**文档级**变量：没有打开文档时读不到（返回 None）。用例期间
  保留一个基线文档就是为了这个。
- 不要用 `Stop-Process -Force` 收尾：会留下 `%TEMP%\*.sv$`，下次启动 AutoCAD
  弹"图形修复"。用 `com.clean_quit()`（关文档 → Quit → 等进程消失）。
- **不要为了让 `(load ...)` 能跑而改 `TRUSTEDPATHS`/`SECURELOAD`**：它们是持久
  变量，忘还原就污染用户配置。需要跑 LISP 时用 `SendCommand` 内联
  `(progn ...)`，不需要任何信任设置。
- 命令卡死的坑：`-LAYERSTATE` 只要动过图层表就永不返回（已放弃该能力）；
  `(command ...)` 在双文档下也可能挂，能用 `(vl-cmdf ...)` 就用它。

## 5. 推代码之前：远端用 SSH

```bash
python scripts/doctor.py          # 5 项自检（含 SSH）
python scripts/install_hooks.py   # 装 pre-push：HTTPS 远端 / 无 SSH key 直接拒推
```

本仓库历史上用 HTTPS 远端时，`git push` 会卡在 `git-credential-manager` 的
不可见凭据弹窗上（表现为无输出挂死）。远端请保持
`git@github.com:Winterwind2017/autocad-agent-kit.git`。

## 6. 文档与代码必须一致

`README.md` 的能力计数由 `python tools/gen_readme_counts.py` 生成，
`docs/UNSUPPORTED.md` 的状态章节由 `python tools/gen_unsupported.py` 生成；
两者都挂在 `pre-push` 钩子上——**文档与代码不一致时推送会被拒绝**。
离线测试 `tests/test_docs.py` 也会核对（防文档漂移）。
