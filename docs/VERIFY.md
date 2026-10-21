# 全量验证记录（VERIFY）

> 目的：任何人在干净机器上，能按下面这几条命令复现"112 条真机通过"。
> 记录时间：2026-10-21（本地时间 Asia/Shanghai）。

## 0. 环境

| 项 | 值 |
|---|---|
| 引擎 | NX 2512 @ `D:\Program Files\Siemens\DesigncenterNX2512` |
| 入口 | `NXBIN\run_journal.exe <journal.py> -nx` |
| 宿主 Python | `C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe` |
| 许可 | `C:\ProgramData\Siemens\siemens_SSQ.dat`（feature 4,420） |
| 内核 | nxkit 0.1.0（本仓库） |
| 技能 | ww-nx-automation |

## 1. 干净 clone（不是工作副本）

```powershell
git clone git@github.com:Winterwind2017/nxkit.git D:\bililive\_verify\nxkit-clone
cd D:\bililive\_verify\nxkit-clone
git log --oneline -1        # 98df998
$env:PYTHONPATH = "D:\bililive\_verify\nxkit-clone\src"
```

## 2. 离线测试与自检

```powershell
python -m pytest -q tests
# 9 passed in 0.09s

python -m nxkit selftest
# 自检通过：112 条能力，动作与判据齐全，负例都能被拒绝

python -m nxkit licenses
# 许可证文件: C:\ProgramData\Siemens\siemens_SSQ.dat
# feature 总数: 4420
# 本机许可覆盖全部已登记能力
```

## 3. 真机全量（干净 clone 里跑）

```powershell
python -m nxkit run --workdir D:\bililive\_verify\rundir
# 112/112 通过  (会话 22.0s, 退出码 1)
```

> 注意：`run_journal` 的**退出码是 1**（NX 特性），结果以 `result.json` 为准。

## 4. 技能仓库

```powershell
cd D:\bililive\ww-nx-automation
python tools/check_skill.py --check
# 技能校验通过：能力名、CLI 命令、数量断言、链接都与 capabilities.json 一致
python -m pytest -q tests
# 4 passed in 0.01s
python tools/sync_capabilities.py
# verified: 112 | pending: 16 | cli: 7
```

## 5. 数字一致性

```powershell
cd D:\bililive\nxkit
python tools/check_consistency.py --skill D:\bililive\ww-nx-automation
# 五处数字一致
```

它核对五处：`README.md`、`docs/CAPABILITY_MATRIX.md`、`docs/STATUS.md`、
`docs/registry.yaml`、技能快照 `capabilities.json`。

## 6. 本轮结果汇总

| 检查 | 结果 |
|---|---|
| 离线测试 | 9 passed |
| 自检（动作/判据/负例） | 112 条，负例全部被拒 |
| 许可扫描 | 4,420 feature，四档齐全 |
| 真机全量（工作副本） | **112/112**，连跑 2 次均通过 |
| 真机全量（干净 clone） | **112/112** |
| 技能校验 + 测试 | 通过 / 4 passed |
| 五处数字一致性 | 一致 |
| L4（存盘→重开→复测） | **52 / 112** |

## 7. 结论

- 能力清单可复现：同一 commit、同一环境，冷启动跑出 112/112。
- 没有"只在工作副本里能过"的能力。
- 没打通的能力全部登记在 `docs/UNSUPPORTED.md`，每条带 NX 返回的错误原文。
