# ww-solidworks-automation

把 **SolidWorks 2025 自动化**做成一份可安装的 Agent 技能：怎么调、怎么证明调对了、
哪些根本别试。

> 执行内核是另一个独立仓库 [swkit](https://github.com/Winterwind2017/solidworks-agent-kit)
> （Python 库 + CLI + MCP）。**本仓库不含执行代码**，只有说明书、判据与方法论，
> 加上几个校验/安装脚本。

## 里面有什么

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能本体：铁律、能力索引、"别试这些"、典型配方、自检三问 |
| `capabilities.json` | 能力快照（150 verified / 25 非 verified / 91 CLI 命令 + 出处 commit） |
| `references/methodology.md` | GB/T 第一角审查、DFM 按工艺检查、自审查、VBA 策略 |
| `references/checklists.md` | 装配类任务的事前/事中/验收清单 |
| `tools/sync_capabilities.py` | 从 swkit 刷新 `capabilities.json` 与技能里的索引（需要内核） |
| `tools/check_skill.py` | 校验技能与快照一致（**不需要内核**，可离线跑） |
| `tools/install_skill.py` | 装到 `~/.dsh/skills`、`~/.cursor/skills`，旧版自动备份 |

## 安装

```bash
git clone git@github.com:Winterwind2017/ww-solidworks-automation.git
cd ww-solidworks-automation
python tools/install_skill.py --check      # 看装没装
python tools/install_skill.py              # 装/更新
python tools/install_skill.py --remove-legacy   # 顺带清掉旧的 solidworks-automation
```

装好后技能目录里会出现 `ww-solidworks-automation`。

## 为什么它值得信

技能最容易出的问题是**撒谎**——写着早就失效的结论，而模型不会质疑它。
所以本仓库对"技能说的"和"内核做的"之间加了三道锁：

1. **能力清单不是手写的**：`capabilities.json` 由 `tools/sync_capabilities.py`
   从内核的 registry 生成，带 `swkit` 版本与内核 commit；
2. **`tools/check_skill.py` 四条规则**：工具名必须在快照里存在；非 verified
   只许出现在"别试这些"区块；`swkit <cmd>` 必须是真子命令；散文里禁止写
   会漂移的数量断言；
3. **测试**：`tests/test_skill.py` 把上面四条 + 索引新鲜度一起跑。

```bash
python tools/check_skill.py --check
python -m pytest tests -q
```

## 刷新能力清单（内核有更新时）

```bash
# 前提：swkit 可 import（pip install -e <内核仓库> 或 PYTHONPATH=<内核>/src）
SWKIT_REPO=<内核仓库路径> python tools/sync_capabilities.py
python tools/check_skill.py --check
git add -A && git commit -m "chore: 同步能力快照"
```

## 许可

MIT，见 [`LICENSE`](LICENSE)。
