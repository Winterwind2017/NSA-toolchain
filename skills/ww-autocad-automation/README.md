# ww-autocad-automation

> **NSA = Non-standard automation（非标自动化）** —— 仓库名与 `nsa_*` 工具前缀都取自这个缩写。
> 本仓是这套工具链的一员：目标是**让做非标自动化设备设计的工程师，能更方便地驱动手边这些软件**，
> 把重复的建模、出图、编号、编程动作交给 agent，精力留在方案、机构与判断上。

把 **AutoCAD 2025 自动化**做成一份可安装的 Agent 技能：怎么调、怎么证明调对了、
哪些根本别试。

> 执行内核是另一个独立仓库 [acadkit](https://github.com/Winterwind2017/autocad-agent-kit)
> （Python 库 + CLI + MCP）。**本仓库不含执行代码**，只有说明书、判据与方法论，
> 加上几个校验/安装脚本。

## 里面有什么

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能本体：铁律、能力索引、"别试这些"、典型配方、自检三问 |
| `capabilities.json` | 能力快照（verified / dead / CLI 命令 + 出处 commit） |
| `references/pitfalls.md` | 13 类实测坑（返回值不可信、命令挂死、几何单位、环境、出图） |
| `references/recipes.md` | 按族的任务配方与判据数字 |
| `references/checklists.md` | 交付前的事前/事中/验收清单 |
| `tools/sync_capabilities.py` | 从 acadkit 刷新 `capabilities.json` 与技能里的索引（需要内核） |
| `tools/check_skill.py` | 校验技能与快照一致（**不需要内核**，可离线跑） |
| `tools/install_skill.py` | 装到 `~/.dsh/skills`、`~/.cursor/skills`，旧版自动备份 |
| `tests/test_skill.py` | 离线测试：校验 + 快照结构 + 索引新鲜度 |

## 安装

```bash
git clone git@github.com:Winterwind2017/ww-autocad-automation.git
cd ww-autocad-automation
python tools/install_skill.py --check      # 看装没装
python tools/install_skill.py              # 装/更新
```

装好后技能目录里会出现 `ww-autocad-automation`。

## 为什么它值得信

技能最容易出的问题是**撒谎**——写着早就失效的结论，而模型不会质疑它。
所以本仓库对"技能说的"和"内核做的"之间加了三道锁：

1. **能力清单不是手写的**：`capabilities.json` 由 `tools/sync_capabilities.py`
   从 acadkit 的 registry + caps 生成，带 acadkit 版本与内核 commit；
2. **`tools/check_skill.py` 五条规则**：能力名必须在快照里存在；非 verified
   只许出现在"别试这些"区块；`acadkit <cmd>` 必须是真子命令；散文里禁止写
   会漂移的数量断言；相对链接必须指向真实文件；
3. **测试**：`tests/test_skill.py` 把上面五条 + 索引新鲜度 + 快照自洽一起跑。

```bash
python tools/check_skill.py --check
python -m pytest tests -q
```

## 刷新能力清单（内核有更新时）

```bash
# 前提：acadkit 可 import（pip install -e <内核仓库> 或 PYTHONPATH=<内核>/src）
ACADKIT_REPO=<内核仓库路径> python tools/sync_capabilities.py
python tools/check_skill.py --check
python -m pytest tests -q
git add -A && git commit -m "chore: 同步能力快照"
```

## 与内核的分工

| 谁 | 负责 |
|---|---|
| acadkit（内核） | 动作实现、判据代码、真机用例、环境自检、CLI/MCP |
| 本技能 | 怎么选能力、怎么读判据、哪些别试、交付前检查什么 |

技能**不 import** acadkit——换成别的机器也能离线安装与校验；只有刷新快照时才需要内核。

## 许可

MIT，见 [`LICENSE`](LICENSE)。
