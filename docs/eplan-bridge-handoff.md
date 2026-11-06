# EPLAN 桥接入手册（等平台装上后照这个做）

> 现状（2026-11-04 09:35 实测）：本机只有 **EPLAN License Client 2024.0.3.225**
> （`C:\Program Files\EPLAN\Common\EClientService.exe`），**没有** Platform / Electric P8，
> 没有 `Eplan.exe`，也没有任何 `Eplan.EplApi.*.dll`。所以桥接链条现在断在第一环。

## 一、整条链长什么样

```
agent ──stdio──> nsa_mcp_hub(s) ──stdio──> servers/eplan_mcp ──代理──> MCP/EPLAN/server.py
                                                                        │
                                                        eplan_mcp/bridge.py（Python 客户端）
                                                                        │  命名管道，定长帧
                                                        EPLAN 进程内 C# Add-in（服务端）
```

### 客户端（Python，已有，可直接读）

`eplan_mcp/bridge.py` + `eplan_mcp/transport.py`：

1. **发现**：扫 `%LOCALAPPDATA%\EplanMcp\instances\*.json`；每个文件必须是
   `{"protocol":1, "instance_id", "pid", "build", "pipe", "exe", "start_filetime_utc", "trial_writes_enabled"}`；
   然后做**身份校验**——用 `OpenProcess` + `QueryFullProcessImageNameW` + `GetProcessTimes`
   确认「pid 的 exe 路径 + 启动时间」与发现文件完全一致（防伪造/复用 pid）；
   再用 `WaitNamedPipeW("\\.\pipe\<pipe>", 100ms)` 确认管道真的在监听。
2. **命名**：管道名必须匹配 `eplan-mcp-<pid>-<32 位 hex>`（正则校验，防止随便连）。
3. **帧格式**：`uint32 小端长度 + UTF-8 JSON`，单帧上限 4 MiB，默认超时 65 s。
4. **请求**：`{"protocol":1, "instance_id", "operation", "payload"}`；
   只读操作 `hello / list_projects / list_pages / list_functions / trial_*_catalog …`，
   其余一律算写操作。
5. **写的三道闸**：`profile=trial`（环境变量）→ 实例的 `trial_writes_enabled=true`
   → `hello` 回的 `build` 必须**精确等于** `2.9.4.14642`（`config.expected_build`）。

### 服务端（C# Add-in，源码在 `MCP/EPLAN/addin/`）

`CodexBridge.cs`（193 KB，2990 行）在 `OnStartup` 里：

```csharp
instanceId = Guid.NewGuid().ToString("N");
pipeName   = "eplan-mcp-" + Process.GetCurrentProcess().Id + "-" + instanceId;
folder     = %LOCALAPPDATA%\EplanMcp\instances;
discovery  = folder\<instanceId>.json;   // protocol/instance_id/pid/build/pipe/gui_thread/
                                         // start_filetime_utc/trial_writes_enabled/exe
listener   = new Thread(Listen)          // NamedPipeServerStream(pipeName, InOut, 1, ...)
```

`OnExit` 删除发现文件。其余 `*.cs` 是同族模块：`BasicFix`、`ClientEngineering`、
`CuratedParts`、`MopParameterFix`、`PageOrder`、`PlcChinese`、`ThreePhase`、
`ReferenceInterfaces`、`RuntimeConfig`。

## 二、装完平台后的四步（脚本都在 `MCP/EPLAN/addin/`）

> 先跑自检，它会告诉你现在卡在第几步：
>
> ```powershell
> python scripts\eplan_preflight.py          # 人看的清单
> python scripts\eplan_preflight.py --json    # 机器读的
> ```
>
> 检查 9 组：环境变量 / 平台本体（env → 常见路径 → 注册表 → PATH）/ 5 个 API 程序集 /
> csc.exe / pywin32 / Add-in 源码与脚本 / 已编译产物 / 发现目录与在跑的 EPLAN /
> private/artifacts。有阻塞项退出码 1，并给出「当前可到第几步 + 最先要解决的两条」。

### 0. 前置检查

```powershell
$env:EPLAN_EXE = 'C:\Program Files\EPLAN\Platform\2.9.4\Bin\Eplan.exe'
$env:EPLAN_BIN = Split-Path -Parent $env:EPLAN_EXE
# 这 5 个必须都在 $EPLAN_BIN 里：
#   Eplan.EplApi.AFu.dll  Baseu.dll  DataModelu.dll  HEServicesu.dll  EServicesu.dll
```

本机已具备：`C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`（✅ 在）
和 venv 里的 pywin32（✅ 在）。缺的只有 EPLAN 平台那 5 个程序集。

### 1. 编译 Add-in

```powershell
powershell -File .\MCP\EPLAN\addin\build.ps1
# 输出：MCP\EPLAN\private\addin\Codex.EplAddin.Bridge.dll
```

脚本用 `/platform:x64 /optimize+ /codepage:65001` 编译 `addin\*.cs`，引用上面 5 个 dll。
DLL 故意不提交（`private/` 在忽略列表里）。

### 2. 注册（EPLAN 必须全关）

```powershell
powershell -File .\MCP\EPLAN\addin\register.ps1 -DllPath <上面那个 dll 的绝对路径>
```

它实际执行：

```
Eplan.exe /Variant:"Electric P8" /NoSplash /Frame:0 /Auto /Quiet EplApiModuleAction /register:"<dll>"
```

脚本会先检查 `Get-Process EPLAN`，**有实例在跑就拒绝**（不替你杀进程）。

### 3. 启动 EPLAN → 验证发现

```powershell
Start-Process $env:EPLAN_EXE -ArgumentList '/Variant:"Electric P8"'
# 然后在 MCP 里：
#   eplan_bridge_discover  → instances 里应出现 1 条（含 pid/build/pipe）
#   eplan_bridge_hello     → 拿到真实 build，和 2.9.4.14642 对一下
#   eplan_projects_list    → 列出已打开的工程
```

### 4. 要写操作才加这一步

```powershell
powershell -File .\MCP\EPLAN\addin\launch-trial.ps1 -Workspace <可丢弃的绝对目录>
```

它会给进程设 `EPLAN_MCP_TRIAL_INSTANCE=1` + `EPLAN_MCP_WORKSPACE=<workspace>` 再启动，
Add-in 据此把发现文件的 `trial_writes_enabled` 写成 `true`。此时才允许 `eplan_trial_*`。

## 三、接上之后我们这边要改的

1. 环境变量：`EPLAN_EXE`（必需）、`EPLAN_BIN`（编译用）、`EPLAN_MCP_WORKSPACE`、
   发布写操作时 `EPLAN_MCP_PROFILE=trial`；
2. 验收：把 `eplan.projects.*` / `eplan.pages.*` 这类真机用例加回来，用
   `skip_if=_eplan_missing`（它查注册表里的**平台**条目，不会被 License Client 骗过）；
3. 建议先跑的只读验证链：
   `eplan_bridge_discover` → `eplan_bridge_hello` → `eplan_projects_list` →
   `eplan_pages_list` → `eplan_functions_list` → `eplan_page_inventory`。

## 四、安全边界（服务端设计，不是我们加的）

* 发现文件只是**线索**，管道握手才算授权；身份校验绑定 exe 路径 + 启动时间；
* 写操作要求 `profile=trial` + 实例 trial 标记 + **精确构建号**，三者缺一不可；
* 超时一律返回 `automatic_retry_allowed: false`，写操作还会附 `native_outcome_unknown: true`；
* `eplan_capabilities` 里 `arbitrary_actions_scripts_reflection: not_exposed`——
  不暴露"执行任意脚本"的口子。
