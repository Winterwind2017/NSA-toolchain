# 迁移记录：13 个单仓 → 1 个 monorepo（2026-11-09）

## 为什么

原来软件自动化相关有 13 个仓（6 内核 + 1 网关 + 6 技能），加起来才 3 MB，但：

- 10 个脚手架文件（`pyproject.toml` / `README.md` / `docs/PITFALLS.md` / `docs/UNSUPPORTED.md` /
  `docs/VERIFY.md` / `tests/test_offline.py` / `.gitignore` / `.gitattributes` / `AGENTS.md` / `LICENSE`）
  在 ≥4 个内核仓里各存一份，**内容还各不相同** → 文档漂移（实例：`tool-surface.md` 写 579 工具，实际 639）；
- 6 个技能仓各自复制了同一套 `tools/{sync_capabilities,check_skill,install_skill}.py`，
  **6 份哈希全不同** → 同一工具有 6 个互不相同的分支；
- 每加一个能力要在 2–3 个仓里改文档。

## 怎么做的

```
nsa-toolchain/                    ← 新仓（私有）
  kernels/{sw,acad,nx,gx,codesys,autoshop}/   ← 6 个内核，git subtree 导入（历史完整保留）
  hub/                                        ← 聚合网关（同上）
  skills/ww-*/                                ← 6 个技能（同上）
  docs/ scripts/                              ← 仓级文档与脚本
```

- 导入方式：`git subtree add --prefix <目标> <旧仓本地路径> main`（逐个，1–2 s/个），
  历史提交作者/时间原样保留，`git log -- kernels/sw` 可查。
- 每个单仓导入前都已确认 `git status` 干净（`ww-autoshop-automation` 有 4 项未提交，
  先单独提交并推送了 `14887f7`）。
- 旧仓的 `.git` 目录在切换时已被删除，**历史只在新仓**；旧远端仓库全部归档（只读保留）。

## 本地路径：目录联接（junction）

为了让**环境变量、脚本、DSH 的 MCP 配置一行都不用改**，老路径全部改成指向新仓的目录联接：

| 老路径 | 现在是 | 指向 |
|---|---|---|
| `D:\bililive\solidworks-agent-kit` | Junction | `nsa-toolchain\kernels\sw` |
| `D:\bililive\acadkit` | Junction | `nsa-toolchain\kernels\acad` |
| `D:\bililive\nxkit` | Junction | `nsa-toolchain\kernels\nx` |
| `D:\bililive\gxkit` | Junction | `nsa-toolchain\kernels\gx` |
| `D:\bililive\codesyskit` | Junction | `nsa-toolchain\kernels\codesys` |
| `D:\bililive\autoshopkit` | Junction | `nsa-toolchain\kernels\autoshop` |
| `D:\bililive\ww-*-automation`（6 个） | Junction | `nsa-toolchain\skills\ww-*` |
| `D:\bililive\nsa-mcp-hub` | **真实目录**（见下） | — |
| `D:\bililive\nsa-mcp-hub` | Junction | `nsa-toolchain\hub` |

### hub 的反向联接是怎么翻正的（2026-11-09 晚间，已完成）

**现状：13 个老路径全部是联接，`nsa-toolchain\hub` 是真实目录。** 下面是踩坑记录，留作以后参考。

一开始删不掉 `D:\bililive\nsa-mcp-hub`（`rmdir` 一直报 `The process cannot access the file`），
于是临时做成反向联接（`nsa-toolchain\hub` → 老路径），保证 hub 的 MCP 端点不断。

排查过程与结论：

1. **杀掉 10 个 hub MCP 子进程也没用**——因为 DSH 会立刻把它们重新拉起来（子进程的 **cwd 就是
   `D:\bililive\nsa-mcp-hub`**，Windows 里进程的当前目录就是一个目录句柄，**目录里有进程以它为 cwd
   就改不了名/删不掉**）；
2. `openfiles` 查不到属主，Restart Manager（`RmGetList`）返回 `ERROR_ACCESS_DENIED`（要管理员）；
3. 真正定位靠 **读 PEB**：`NtQueryInformationProcess` → `PEB.ProcessParameters.CurrentDirectory.DosPath`，
   扫全部进程，发现 **11 个进程**（9 个 kit 子进程 + hub 父进程 + 1 个服务）的 cwd 都在该目录；
4. 最终做法是**在同一个进程里**完成：枚举并 `TerminateProcess` 所有 cwd 持有者 →（DSH 可能会重新拉起，
   所以循环重试最多 20 次）→ `os.rename` 把整个目录搬进 `nsa-toolchain\hub` → `mklink /J` 把老路径
   指回来。第 1 次就成功（杀了 11 个进程）。

> 关键教训：**光"杀进程"不够，必须在同一个动作里杀掉 + 改名**；分开两步的话，DSH 的按需重启会
> 在两步之间把句柄重新装上。

`scripts\flip-hub-junction.ps1` 保留下来备查（也能在将来万一又出现反向联接时用），
但它只做"探测 + 改名"，**不做杀进程**——真正可靠的做法是上面那个"杀+改名"一条龙。

翻正后复核：

- `nsa-toolchain\hub`：真实目录；`D:\bililive\nsa-mcp-hub`：Junction → 它；
- hub 端点照常工作：`nsa_hub_status` 9 kit、`codesys_ping` OK（经联接 spawn 正常）；
- monorepo `git status` 仍干净（`_runs` / `_archive` 等运行产物被 .gitignore 忽略）。

## 验证

```powershell
.\scripts\verify-migration.ps1     # 检查 13 个联接 + hub 方向 + 内容一致性 + git 干净
```

实测（2026-11-09）：

- monorepo：**566 个 tracked 文件 / 525 个提交**，`git status` 干净；
- 老路径全部可读：`nsa-mcp-hub` 导入正常、codesys kit 报 **60 个工具**；
- `hub` 的 `KITS` 仍是 9 个（acad/autoshop/catia/codesys/eplan/gx/nx/sw/ug）。

## GitHub 上的旧仓：归档 → 删除

归档后这 13 个仓在账号里仍然各占一行、内容也与 monorepo 重复，所以按"整理后没有意义"处理：

| 旧仓 | 内容去处 | 校验 |
|---|---|---|
| `solidworks-agent-kit` | `kernels/sw` | HEAD `6d6f1962` 已是 monorepo 祖先 |
| `autocad-agent-kit` | `kernels/acad` | `62e70f63` |
| `nxkit` | `kernels/nx` | `b33cb883` |
| `gxkit` | `kernels/gx` | `0a039466` |
| `codesyskit` | `kernels/codesys` | `cc7c05fa` |
| `autoshopkit` | `kernels/autoshop` | `8392c540` |
| `ww-solidworks-automation` | `skills/…` | `f269d6b4` |
| `ww-autocad-automation` | `skills/…` | `5908b2c2` |
| `ww-nx-automation` | `skills/…` | `b9e1b0c4` |
| `ww-gxworks-automation` | `skills/…` | `091a214c` |
| `ww-codesys-automation` | `skills/…` | `a1b942bf` |
| `ww-autoshop-automation` | `skills/…` | `14887f7e` |
| `nsa-mcp-hub` | `hub` | `1b817d2a`；**另一条独立历史**已存为分支 `archive/hub-remote-20261106`（`26428fc`，21 提交） |

删除需要一个 `delete_repo` 权限（当前 `gh` 的 OAuth token 只有
`gist / read:org / repo / user / workflow`，直接调 API 返回 403）：

```powershell
gh auth refresh -h github.com -s delete_repo     # 浏览器里授权一次
# 然后逐个删除（或按脚本批量）
gh repo delete Winterwind2017/<旧仓名> --yes
```

**保留的仓库**（不属于这条工具链，各有用途，不要删）：

- `Non-standard-automation-design` —— 设计工作台（流程、规则、案例）
- `workspace-assets` / `global-assets` —— 工作区级 / 全局资产与配置
- `ww-obsidian`（obsidiankit 技能）与 `ww-obsidian-agent`（Obsidian 内的对话插件，**不是同一层**）
- `dsh-sidebar-edge`（DSH 侧边栏插件）
- `skill-nonstandard-project-manager` / `skill-management-advisor` / `value-investing-skills`

## 发版约定

单仓时代每个仓一个 `v1.0`；现在用 **tag 前缀**区分：

```
sw-v1.2.0       内核独立发版
acad-v0.9.0
hub-v0.16.0
toolchain-v1.0  整包里程碑
```
