# 上游同步手册（CAD-Agent-Hub → 本地快照 + 我们的补丁）

本地 `D:\bililive\CAD-Agent-Hub` **不是 clone**，是「上游快照 + 我们叠的补丁」。
所以每次同步要能回答三个问题，`scripts/sync_upstream.py` 逐条验：

1. 基线是哪次上游提交？
2. 本地相对上游到底动了什么？
3. **我们的补丁还能不能原样重放**（重放结果必须与本地逐字节一致）。

## 用法

```powershell
python scripts\sync_upstream.py                  # 只检查（默认，只读）
python scripts\sync_upstream.py --verify         # 只验补丁重放等价性
python scripts\sync_upstream.py --regen-patches  # 重新生成 docs\patches\*.patch
python scripts\sync_upstream.py --apply --yes    # 真同步：备份 → 换文件 → 重放补丁 → 编译
python scripts\sync_upstream.py --ref 2.9.1      # 指定上游分支/tag
```

当前实测（2026-11-04，上游 `c051b7272af331fe30c7dbf5932d4086514211a3`）：

```
[UG] 上游 61 / 本地 61
  内容不同 2：nx_remote_ops.py, server.py
[Solidworks] 与上游一致（38 个文件）
[CATIA] 与上游一致（41 个文件）
[EPLAN] 与上游一致（69 个文件）

差异合计 2 个文件（含我们自己的补丁）
[UG] 本地重编译的二进制 3 个（不同步，同源码不同构建元数据）
     dotnet_bridge\bin\NXMcPRemotingServer.dll 等

补丁重放验证：通过
  apply ug.patch → rc=0
  补丁重放结果与本地逐字节一致（2 个文件）
```

## 三条硬规则（都是踩出来的）

### 1. 文本比较必须规范化换行

上游是 git checkout，Windows 上 `core.autocrlf` 给的是 **CRLF**；本地快照是 **LF**。
第一版脚本直接比原始字节，结果 UG **61/61 全判成"内容不同"**。
现在 `sha()` 对非二进制文件先 `\r\n → \n` 再算哈希。

### 2. 补丁只收「上游有、本地也改了」的文件

补丁的语义是**我们叠加在上游上的改动**。本地新增的东西（自己的脚本、NX 存出来的
`.prt`、日志、截图）不属于补丁，同步时也不该被覆盖：

* 生成补丁时只看 `modified`（两侧都存在且内容不同）；
* `kit_files()` 排除 `workspace/`、`private/`、`logs/`、`output/`、`__pycache__`，
  以及 `.prt/.log/.dxf/.png/.pdf/.stp/...` 这些产物后缀。

第一版没排除，产出过 108 KB 的补丁，里面混着 `nsa_verify_cam.prt` 之类的产物。

### 3. 二进制产物不同步

`MCP/UG/dotnet_bridge/bin/*.dll|exe` 是本地**重编译**出来的（同源码、不同构建元数据，
大小一样但哈希不同）。它们不进补丁也不被覆盖，只在检查时列出来提醒。

## 补丁格式

`docs/patches/<kit>.patch`，路径是 `a/MCP/<kit>/...` / `b/MCP/<kit>/...`，
所以可以直接：

```powershell
cd D:\bililive\CAD-Agent-Hub
git apply -p1 ..\nsa-mcp-hub\docs\patches\ug.patch
```

（`git apply` 在非 git 目录里也能用。）当前只有 `ug.patch`（11.9 KB，2 个文件：
`nx_remote_ops.py` 的 CAM 配方 + `server.py` 的 `floor_z` 等参数）。

## 上游真出新提交时怎么走

1. `python scripts\sync_upstream.py` —— 看差异清单；若某个我们改过的文件上游也改了，
   补丁重放会**失败并报出是哪个文件**；
2. 冲突就先在本地把该文件对齐上游版本，再重新应用我们的改动，
   然后 `--regen-patches` 重生成补丁；
3. `--verify` 必须通过；
4. 最后 `--apply --yes` 真同步（会先备份成 `_snapshot-MCP-<kit>-<时间戳>`），
   脚本会自动 `py_compile` 所有同步过的 `.py`；
5. 同步完跑相关验收：
   `python -m nsa_mcp_hub.acceptance --kit ug --kit eplan --kit sw`。
