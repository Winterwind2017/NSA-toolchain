# P1 进度

只记录**已经能跑**的东西，不写计划。每条附验证方式。

## ✅ 步骤 1：包骨架 + `acadkit status` 环境自检

**产出**

```
src/acadkit/
├─ __init__.py          版本
├─ registry.py          载入 docs/registry.yaml（有 PyYAML 用之，无则容错解析）
├─ status.py            环境自检：采集 + 判定 + 渲染
├─ core/com.py          只附加不启动；clean_quit
└─ cli/main.py          status / env-baseline / env-check / registry / selftest
tests/test_offline.py   14 条离线测试（不需要 AutoCAD）
tests/live_env_check.py 真机链路：基线 → 漂移 → 检出 → 还原 → 退出
pyproject.toml          console_script = acadkit
```

**命令**

```bash
acadkit selftest        # 离线自检（registry 60 条 + 校验）
acadkit registry        # 能力清单（--status verified 等）
acadkit status          # 环境自检（只附加，不启动 AutoCAD）
acadkit env-baseline    # 采环境基线 → ~/.acadkit/env_baseline.json
acadkit env-check       # 与基线比对
```

**退出码**：`0` 通过 · `3` AutoCAD 未运行（只读命令的正常结果）· `4` 环境不合规
（profile≠`<<VANILLA>>` 或多实例）· `5` 环境漂移。

## 真机验证记录（2026-10-21）

| 用例 | 期望 | 实测 |
|---|---|---|
| AutoCAD 未运行时 `status` | 只报告、不启动、rc=0 | ✅ 跑完进程数仍为 0 |
| AutoCAD 运行中 `status` | 读到 profile=`<<VANILLA>>`、单实例 OK | ✅ |
| `env-baseline` | 写基线文件 | ✅ `C:\Users\yuche\.acadkit\env_baseline.json` |
| 改 `MEASUREMENT` 1→0 后 `env-check` | 检出 1 项漂移、rc=5 | ✅ `var:MEASUREMENT '1' → '0'` |
| 还原后 `env-check` | 干净、rc=0 | ✅ |
| `clean_quit` | 进程真消失、不留 `.sv$` | ✅ `process_exited=True`，等 1.8 s，`.sv$`=0 |

## 途中修掉的四个真问题（都是跑出来的，不是想出来的）

1. **`dynamic.Dispatch` 会启动 AutoCAD**
   一次 `status` 探测凭空拉起隐藏实例（`Visible=False`，自带 `Drawing1.dwg`）。
   → 改为 `GetActiveObject` 只附加；启动必须显式。
2. **`Documents` 晚绑定下不可枚举**
   `list(app.Documents)` 抛 `TypeError: This object does not support enumeration`。
   → 按索引 `Documents.Item(i)` 取。
3. **未保存文档会让 `Quit()` 弹模态卡死**
   → `save=False` 时先把 `doc.Saved = True`（丢弃修改）。
4. **`Quit()` 是异步的**
   调用返回后进程还活几秒，下一个用例会看到"幽灵实例"。
   → 轮询等进程消失，返回 `process_exited`。

另外把「读不到变量」与「变量为空」分开显示（`（读不到）` vs `（空）`）——
环境漂移判据依赖这个区别。

## 下一步（P1 剩余）

| 步 | 内容 | 估时 |
|---|---|---|
| 2 | `judges/`：按 `JUDGE_SPEC.md` 四级判据，先做 8 个族 | 0.5 天 |
| 3 | `verified` 30 条里的前 12 条落成 CLI + 真机用例 | 1 天 |
| 4 | 环境自检接入每个用例（前后各一次） | 0.5 天 |
| 5 | 22 条 `usable_unjudged` 补到 L2 | 1.5 天 |
