# MIGRATION —— 五个来源 → 一个仓库

> 原则：**不整包搬运，只搬"实测通过 + 有判据"的部分**；没复核的先用透传包住并标红。

## 来源清单

| # | 来源 | 位置 | 体量 | 进入本仓库的方式 |
|---|---|---|---|---|
| ① | 第三方 MCP（fork） | `D:\bililive\Solidworks-MCP-Server` | 188 工具 / 316 KB | 只继承**工具名与分组**；实现按实测重写，错误清单见 `docs/UNSUPPORTED.md` |
| ② | 自有对象框架 | `D:\bililive\DeepCode\cad_framework` | `sw_app.py` 50 KB 等 | `api/app.py`、`core/base.py`、`core/errors.py`、`api/advanced.py` **整体移植**（本人作品，MIT） |
| ③ | 仿真/运动/元数据 MCP | `D:\bililive\mcp-patches`（`sw_sim`/`sw_motion`/`swdm_lite`/`sw_ovba`/`sw_adv`） | 15 工具 | **待合并**为 `swkit.study` / `swkit.meta`（见下） |
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
| `src/swkit/registry.py` | ⑤ 台账（35 verified / 2 unstable / 4 broken） | ✅ |
| `src/swkit/mcp/server.py` | ①的形态 + 新增分层 | ✅ Tier A + Tier B |
| `src/swkit/cli/main.py` | ④的 46 命令收敛为子命令（起步） | ✅ 6 个子命令 |
| `docs/RECIPES.md` | ⑤ 配方 | ✅ 5 条 |
| `docs/PITFALLS.md` | ⑤ 教训 | ✅ 13 条 |
| `docs/UNSUPPORTED.md` | ⑤ 证伪依据 | ✅ |
| `skills/solidworks-automation/` | 新增 | ✅ |

## 待搬迁（按优先级）

1. **③ 仿真/运动/元数据**（`sw_sim` / `sw_motion` / `swdm_lite` / `sw_ovba` / `sw_adv`）
   → 目标 `swkit/study/`（静力研究、网格、求解、读结果）与 `swkit/meta/`
   （DocumentMgr 索引、属性、VBA/OVBA 读取、API 审计）。
   **注意**：子进程调用必须 `stdin=subprocess.DEVNULL`（否则 MCP 调用会挂满超时）。
2. **④ 其余已验证命令**（`sw_fixpack.py` 46 条里尚未进 `verified/` 的部分）
   → 逐条搬成函数 + 在 `registry.py` 登记证据；优先出图类与特征类。
3. **④ 回归脚本** `_sw_probe/regress.py`（28 项）
   → `tests/regress.py`，加 `@pytest.mark.live`，跑前强制 `CloseAllDocuments`。
4. **⑤ 精简探针**：`tlb_explore.py`（TLB 反射）、`chmread.py`（官方帮助检索）
   → `src/swkit/diagnostics/`。其余实验脚本**不进仓库**。
5. **① 剩余 ~80 个未复核工具** → 复核后二选一：进 `verified/` 或写进 `UNSUPPORTED.md`。

## 明确不做

- 不把 `_sw_probe` 的 310 个实验脚本放进仓库（噪声，且大量与最终结论无关）。
- 不把 AutoCAD / NX / Photoshop 部分搬进来（它们在 `DeepCode/cad_framework` 里继续维护）。
- 不保留上游那批"调用不存在方法"的实现（只在 `UNSUPPORTED.md` 里记录事实）。
