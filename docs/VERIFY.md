# 全量验证记录（VERIFY）

> 目的：任何人在干净机器上，能按下面这几条命令复现"146 条真机通过"。
> 最近复跑：2026-10-22 09:00（Asia/Shanghai），干净 clone @ `dc50239`。

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
git clone git@github.com:Winterwind2017/nxkit.git D:\bililive\_verify3\clone
cd D:\bililive\_verify3\clone
git log --oneline -1        # dc50239
$env:PYTHONPATH = "D:\bililive\_verify3\clone\src"
```

## 2. 离线测试与自检

```powershell
python -m pytest -q tests
# 9 passed in 0.09s（干净 clone 实测）

python -m nxkit selftest
# 自检通过：146 条能力，动作与判据齐全，负例都能被拒绝

python -m nxkit licenses
# 本机许可覆盖全部已登记能力
```

## 3. 真机全量（干净 clone 里跑）

```powershell
python -m nxkit run --workdir D:\bililive\_verify3\runs\full
# 146/146 通过  (会话 47.9s, 退出码 1)（干净 clone 实测）
```

> 注意：`run_journal` 的**退出码是 1**（NX 特性），结果以 `result.json` 为准。

## 4. 技能仓库

```powershell
cd D:\bililive\ww-nx-automation
python tools/check_skill.py --check
# 技能校验通过：能力名、CLI 命令、数量断言、链接都与 capabilities.json 一致
python -m pytest -q tests
# 4 passed
python tools/sync_capabilities.py
# verified: 146 | pending: 17 | cli: 7
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
| 自检（动作/判据/负例） | 146 条，负例全部被拒 |
| 许可扫描 | 4,420 feature，四档齐全 |
| 真机全量（工作副本） | **146/146**，连续 2 次全绿 |
| 真机全量（干净 clone） | **145/145**（`00f444a`，18.8 s） |
| 技能校验 + 测试 | 通过 / 4 passed |
| 五处数字一致性 | 一致 |
| L4（存盘→重开→复测） | **54 / 130** |

## 6.1 稳定性：连续多次全量

| 来源 | 结果 | 会话时长 | 失败 |
|---|---|---|---|
| 工作副本 run1 | 145/145 | 18.8 s | 0 |
| 工作副本 run2 | 145/145 | 18.7 s | 0 |
| 干净 clone | 145/145 | 18.8 s | 0 |

会话时长随能力数增长；145 条时约 19 s（历史：114 条时 22 s 左右，
差异主要来自每次会话的 NX 启动开销波动，不是能力耗时）。

## 7. 结论

- 能力清单可复现：同一 commit、同一环境，冷启动 clone 跑出 145/145。
- 没有"只在工作副本里能过"的能力。
- 没打通的能力全部登记在 `docs/UNSUPPORTED.md`，每条带 NX 返回的错误原文。
