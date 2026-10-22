# 全量验证记录

> 目的：在一台装了 GX Works3 的机器上，按下面几步就能复现"6 条能力全过"。

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
# 自检通过：6 条能力，动作与判据齐全

# 2) 离线测试
python -m pytest -q tests
# 7 passed

# 3) 真机全量（约 7–8 分钟；会起停 GX Works3 共 7 次）
python -m gxkit run --workdir D:\bililive\gxkit\_runs\s7
#   PASS project.new              60.9s
#   PASS project.save             50.3s
#   PASS project.meta             49.6s
#   PASS program.paste_st         97.4s
#   PASS build.convert_all        77.2s
#   PASS project.reopen           91.8s
# 6/6 通过  (会话 427.1s)
```

## 历史记录

| 日期 | 结果 | 会话时长 |
|---|---|---|
| 2026-10-22 | 6/6 | 439.8 s |
| 2026-10-22 | 6/6 | 427.1 s |

## 单条验证

```powershell
python -m gxkit run --only project.save --workdir D:\tmp\one
python -m gxkit meta D:\tmp\one\project_save.gx3
# {"config": {"Unit": "FX5U", "UnitId": "528"}, "progress": {...}}
```
