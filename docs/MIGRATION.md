# MIGRATION —— 五个来源 → 一个仓库

> 原则：**不整包搬运，只搬"实测通过 + 有判据"的部分**；没复核的先用透传包住并标红。

## 来源清单

| # | 来源 | 位置 | 体量 | 进入本仓库的方式 |
|---|---|---|---|---|
| ① | 第三方 MCP（fork） | `D:\bililive\Solidworks-MCP-Server` | 188 工具 / 316 KB | 只继承**工具名与分组**；实现按实测重写，错误清单见 `docs/UNSUPPORTED.md` |
| ② | 自有对象框架 | `D:\bililive\DeepCode\cad_framework` | `sw_app.py` 50 KB 等 | `api/app.py`、`core/base.py`、`core/errors.py`、`api/advanced.py` **整体移植**（本人作品，MIT） |
| ③ | 仿真/运动/元数据 MCP | `D:\bililive\mcp-patches`（`sw_sim`/`sw_motion`/`swdm_lite`/`sw_ovba`/`sw_adv`） | 15 工具 | **已合并**：`swkit/study` + `swkit/meta` + `_legacy`（见"③ 的落地方式"） |
| ④ | 实测修复层 | `D:\bililive\mcp-patches\sw_fixpack.py` | 46 命令 / 153 KB | 已验证条目进 `verified/` + `registry.py`；其余命令逐条迁移 |
| ⑤ | 知识资产 | `_sw_probe`（310 探针）+ 11 份 `SW_*.md`（台账 109 KB） | ~1000 文件 | 结论进 `docs/`（RECIPES / PITFALLS / UNSUPPORTED）；只留**精简探针**在 `diagnostics/` |

## 已搬迁（v0.1）

| 目标文件 | 来源 | 状态 |
|---|---|---|
| `src/swkit/core/base.py` | ② `cad_framework/base.py` | ✅ 已搬，导入已改 |
| `src/swkit/core/errors.py` | ② `errors.py` | ✅ |
| `src/swkit/api/app.py` | ② `sw_app.py` | ✅ 导入改为 `..core.*` |
| `src/swkit/api/advanced.py` | ② `sw_advanced.py` | ✅（纯计算，无 COM） |
| `src/swkit/core/com.py` | 新增 | ✅ 双栈桥接 / VARIANT 辅助 / `val()` |
| `src/swkit/core/marks.py` | 新增（来自官方 Remarks 表的实测） | ✅ |
| `src/swkit/verified/assembly.py` | ④ `sw_fixpack.py` 的 round-40 配方 | ✅ 组件线性/圆形阵列 + 镜像 |
| `src/swkit/verified/_common.py` | ④ `_counts`/`_faces`/`_pick_face`/`_wrap`/`_exit_sketch` | ✅ 封装为公共层 |
| `src/swkit/verified/part.py` | ④ 零件/特征 7 条 | ✅ bbox/screenshot/shell/split_line/thicken/offset/特征阵列（真机 8/8） |
| `tests/part_check.py` | 新增 | ✅ 零件侧真机验收（8 项） |
| `src/swkit/registry.py` | ⑤ 台账（35 verified / 2 unstable / 4 broken） | ✅ |
| `src/swkit/mcp/server.py` | ①的形态 + 新增分层 | ✅ Tier A + Tier B |
| `src/swkit/cli/main.py` | ④的 46 命令收敛为子命令（起步） | ✅ 6 个子命令 |
| `docs/RECIPES.md` | ⑤ 配方 | ✅ 5 条 |
| `docs/PITFALLS.md` | ⑤ 教训 | ✅ 13 条 |
| `docs/UNSUPPORTED.md` | ⑤ 证伪依据 | ✅ |
| `skills/solidworks-automation/` | 新增 | ✅ |
| `src/swkit/study/{sim,motion}.py` | ③ `sw_sim.py` / `sw_motion.py` | ✅ 适配层（受管子进程） |
| `src/swkit/meta/{docs,props,vba}.py` | ③ `swdm_lite.py` / `sw_adv.py` / `sw_ovba.py` | ✅ 适配层 |
| `src/swkit/_legacy/*.py` | ③ 原脚本（只改硬编码路径） | ✅ 5 个，共 ~96 KB |

## ③ 的落地方式（为什么是"适配层"而不是重写）

这 5 个脚本的结论**是在当前形态下实测出来的**（Sim 的网格安全档、Motion 的 `GetResults(4)`、
DocumentMgr 的索引结构）。重写成库内函数就必须**重新验证一遍**，风险与工时都大于收益。

做法：
1. 原样收进 `src/swkit/_legacy/`，**只**改三处本机硬编码：
   `VENDOR` → `SWKIT_VENDOR`、`DEFAULT_OUT` → `SWKIT_OUT`、`DB` → `SWKIT_DM_DB`（并保留旧索引回退）。
2. 用 `_legacy/runner.py` 以**受管子进程**调用：`stdin=DEVNULL`（否则 MCP 调用会挂满超时）、
   显式超时、`utf-8/replace`、`cwd=~/.swkit`。
3. `swkit.study` / `swkit.meta` 只做**参数翻译 + 输出解析 + 结构化返回**。

副作用：包体多 ~96 KB。可接受；将来逐条内联时记得同步删掉 `_legacy`。

**顺带修掉一个上游 bug**：`sw_extra_mcp.swdm_query(text)` 传的是 `--text`，而 `swdm_lite.query`
根本没有这个参数（只有 `--prop/--dir/--ext`）→ 带 text 调用必失败。本仓库适配层用真实参数。

## 待搬迁（按优先级）
2. **④ 其余已验证命令**：零件/特征 7 条已搬（见上）；**下一批是出图类**（中心线、中心标记、
   注释、孔表、基准/形位公差/焊接/粗糙度、辅助视图、剖视、断裂视图、尺寸）。
3. **④ 回归脚本** `_sw_probe/regress.py`（28 项）
   → `tests/regress.py`，加 `@pytest.mark.live`，跑前强制 `CloseAllDocuments`。
4. **⑤ 精简探针**：`tlb_explore.py`（TLB 反射）、`chmread.py`（官方帮助检索）
   → `src/swkit/diagnostics/`。其余实验脚本**不进仓库**。
5. **① 剩余 ~80 个未复核工具** → 复核后二选一：进 `verified/` 或写进 `UNSUPPORTED.md`。

## 明确不做

- 不把 `_sw_probe` 的 310 个实验脚本放进仓库（噪声，且大量与最终结论无关）。
- 不把 AutoCAD / NX / Photoshop 部分搬进来（它们在 `DeepCode/cad_framework` 里继续维护）。
- 不保留上游那批"调用不存在方法"的实现（只在 `UNSUPPORTED.md` 里记录事实）。
