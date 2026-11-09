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
| `D:\bililive\nsa-toolchain\hub` | Junction | `D:\bililive\nsa-mcp-hub` |

### 为什么 hub 是反的

切换时 `D:\bililive\nsa-mcp-hub` 被一个进程占着（句柄没释放：`rmdir` 一直报
`The process cannot access the file`）。排查结论（2026-11-09 实测）：

- 把 **10 个 hub MCP 子进程全杀掉**后仍然占用 → 占用者**不是** MCP 子进程；
- `openfiles` 查不到，Restart Manager（`RmGetList`）返回 `ERROR_ACCESS_DENIED`
  —— 需要管理员权限才能列出属主；
- 推断是 **DSH 本体**（宿主进程曾把工作目录切到该路径，Windows 进程的 cwd 就是一个目录句柄）。

所以这一项只能在 **DSH 重启之后**（或重启机器后）完成。为了不让 hub 的 MCP 端点在迁移期间不可用，
改成**反向联接**：

- 内容实体仍在 `D:\bililive\nsa-mcp-hub`（旧路径，DSH 配置不用动）；
- `nsa-toolchain\hub` 是指向它的联接，`git status` 依然干净、文件依然被本仓跟踪。

等占用释放（重启 DSH 或重启机器后），跑一次下面的脚本就能把方向翻正：

```powershell
.\scripts\flip-hub-junction.ps1            # 试运行：只检查占用是否释放
.\scripts\flip-hub-junction.ps1 -Apply     # 真翻：老路径变联接，实体回到 monorepo
```

脚本自带保护：先探测能否改名，不能就退出码 2 并提示；`-Apply` 时才动联接。

## 验证

```powershell
.\scripts\verify-migration.ps1     # 检查 13 个联接 + 内容一致性 + git 干净
```

实测（2026-11-09）：

- monorepo：**521 个提交 / 563 个 tracked 文件**，`git status` 干净；
- 老路径全部可读：`nsa-mcp-hub` 导入正常、codesys kit 报 **60 个工具**；
- `hub` 的 `KITS` 仍是 9 个（acad/autoshop/catia/codesys/eplan/gx/nx/sw/ug）。

## 发版约定

单仓时代每个仓一个 `v1.0`；现在用 **tag 前缀**区分：

```
sw-v1.2.0       内核独立发版
acad-v0.9.0
hub-v0.16.0
toolchain-v1.0  整包里程碑
```
