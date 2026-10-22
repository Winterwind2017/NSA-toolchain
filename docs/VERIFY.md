# 全量验证记录

> 目的：在一台装了 GX Works3 的机器上，按下面几步就能复现"9 条能力全过"。

## 环境

| 项 | 值 |
|---|---|
| 引擎 | GX Works3 1.117.0.1 @ `D:\Program Files (x86)\MELSOFT\GPPW3\GXW3.exe` |
| 宿主 Python | `C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe` |
| 依赖 | `pywin32`、`comtypes`、`Pillow`（UIA 走 `comtypes` 生成 `UIAutomationClient`） |
| 目标机型 | FX5U（`FX5CPU` 系列），程序语言 ST |

## 步骤

```powershell
$env:PYTHONPATH='D:\bililive\gxkit\src'

# 1) 离线自检（不需要打开软件）
python -m gxkit selftest
# 自检通过：9 条能力，动作与判据齐全

# 2) 离线测试
python -m pytest -q tests
# 7 passed

# 3) 真机全量（约 13 分钟；每条能力一个干净会话）
python -m gxkit run --workdir D:\bililive\gxkit\_runs\v1
```

## 单条验证

```powershell
python -m gxkit run --only batch.projects --workdir D:\tmp\one
python -m gxkit meta D:\tmp\one\project_save.gx3
# {"config": {"Unit": "FX5U", "UnitId": "528"}, "progress": {...}}
```

## 历史记录

| 日期 | 结果 | 会话时长 |
|---|---|---|
| 2026-10-22 | 6/6（v0.1） | 439.8 s |
| 2026-10-22 | 6/6（v0.1） | 427.1 s |
| 2026-10-22 | 9/9（v0.2） | 793.3 s |
| 2026-10-22 | 8/9（v0.2，error_detail 偶发粘贴未落地） | 824.8 s |
| 2026-10-22 | 9/9（v0.2，error_detail 加固后） | 816.6 s |
| 2026-10-22 | 9/9（v0.2，加固后第二次） | 817.6 s |

## v0.2 新增三条的单独记录

| 能力 | 会话时长 | 读数 |
|---|---|---|
| `build.program_check` | 97.9 s | `verdict="程序检查已完成。\n无错误。"`, `errors=0`, `clean=True` |
| `build.error_detail` | 103.8 s / 103.9 s（两次） | `errors=1`, `warnings=0`, `failed_stage="程序(ProgPou)转换中"`, `good_steps=17` |
| `batch.projects` | 180.0 s | `items=3`, `clean_items=3`, `distinct_sizes=3`, 内部 129.7 s |

> `build.error_detail` 第一版只贴坏代码就转换，出现过一次 `errors=None`：
> 粘贴没落地或保存没刷新日志。现在会先贴好代码确认"通路是通的"（`good_steps=17`），
> 再贴坏代码；日志没刷新就再转换/保存一轮。此后两次连跑读数一致。
