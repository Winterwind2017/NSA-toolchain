# ww-nx-automation

> **NSA = Non-standard automation（非标自动化）** —— 仓库名与 `nsa_*` 工具前缀都取自这个缩写。
> 本仓是这套工具链的一员：目标是**让做非标自动化设备设计的工程师，能更方便地驱动手边这些软件**，
> 把重复的建模、出图、编号、编程动作交给 agent，精力留在方案、机构与判断上。

把 **UG NX 2512 自动化**做成一份可安装的 Agent 技能：怎么调、怎么证明调对了、
哪些还没打通。

> 执行内核是另一个独立仓库 [nxkit](https://github.com/Winterwind2017/nxkit)
> （Python 库 + CLI）。**本仓库不含执行代码**，只有说明书、判据与方法论，
> 加上几个校验/安装脚本。

## 里面有什么

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能本体：铁律、能力索引、"还没打通"、典型配方、自检三问 |
| `capabilities.json` | 能力快照（verified / pending / CLI + 出处 commit） |
| `references/pitfalls.md` | 8 类实测坑（Null 哨兵、集合、拉伸、制图、导出、许可证） |
| `references/recipes.md` | 按族的任务配方与判据数字 |
| `references/checklists.md` | 交付前的事前/事中/验收清单 |
| `tools/sync_capabilities.py` | 从 nxkit 刷新快照与技能索引（需要内核） |
| `tools/check_skill.py` | 校验技能与快照一致（**不需要内核**，可离线跑） |
| `tools/install_skill.py` | 装到 `~/.dsh/skills`、`~/.cursor/skills` |
| `tests/test_skill.py` | 离线测试：校验 + 快照结构 + 索引新鲜度 |

## 安装

```bash
git clone git@github.com:Winterwind2017/ww-nx-automation.git
cd ww-nx-automation
python tools/install_skill.py --check
python tools/install_skill.py
```

## 为什么它值得信

1. **能力清单不是手写的**：`capabilities.json` 由 `tools/sync_capabilities.py`
   从 nxkit 的能力表生成，带 nxkit 版本与内核 commit；
2. **`tools/check_skill.py` 五条规则**：能力名必须存在；pending 只许出现在
   "还没打通"区块；`nxkit <cmd>` 必须是真子命令；散文里禁止写会漂移的数量断言；
   相对链接必须指向真实文件；
3. **测试**：`tests/test_skill.py` 把上面五条 + 索引新鲜度 + 快照自洽一起跑。

```bash
python tools/check_skill.py --check
python -m pytest tests -q
```

## 刷新能力清单（内核有更新时）

```bash
# 前提：nxkit 可 import
NXKIT_REPO=<nxkit 仓库路径> python tools/sync_capabilities.py
python tools/check_skill.py --check
```

## 与内核的分工

| 谁 | 负责 |
|---|---|
| nxkit（内核） | 动作实现、判据、真机会话、CLI |
| 本技能 | 怎么选能力、怎么读判据、哪些别试、交付前检查什么 |

## 许可

MIT，见 [`LICENSE`](LICENSE)。
