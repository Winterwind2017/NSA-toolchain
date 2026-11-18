# acadkit .NET 通道（进程内插件）

ActiveX/命令行够不着的能力，只能走**进程内托管代码**。这个目录是那条通道。

## 现状

| 命令 | 能力 | 状态 |
|---|---|---|
| `ACADKITVERSION` | 证明插件已加载 | ✅ 实测 |
| `ACADKITREVOLVE` | `solid.revolve`：`Solid3d.CreateRevolvedSolid` | ✅ 实测，体积误差 0.0 |
| `ACADKITLAYERSTATE` | `layer.state`：`LayerStateManager` 保存/改/恢复 | ✅ 实测，颜色读回交叉校验通过 |
| `ACADKITINFO` | 列出已注册命令 | ✅ 实测 |
| `ACADKITEDITBLOCK` | `block.edit_inplace` | ⛔ 占位（BlockEditor 需 UI 模式） |
| `ACADKITASSOC` | `dim.associative` | ⛔ 占位（需要 DimAssoc + 几何关联表） |

## 构建

```bash
python dotnet/build.py            # 需要 .NET SDK 8+ 与 AutoCAD 2025 安装
python dotnet/build.py --check    # 只查工具链
```

产物：`dotnet/bin/Release/AcadKit.Plugin.dll`（`net8.0-windows`，引用 `acdbmgd/acmgd/accoremgd`，`Private=false`，不复制 Autodesk 的 DLL）。

## 加载（三条路，只有第三条走通）

| 方式 | 结果 |
|---|---|
| `_.NETLOAD "path"`（命令行 / LISP `vl-cmdf`） | ❌ **弹模态文件对话框，SendCommand 永久阻塞**（`FILEDIA=0` 也不行） |
| Autoloader bundle → `%APPDATA%\Autodesk\ApplicationPlugins\` | ❌ 命令仍"未知命令" |
| **注册表 `LOADCTRLS=2` + DLL 放 AutoCAD 安装目录** | ✅ **可用** |

根因：`SECURELOAD=1` 且 `TRUSTEDPATHS` 为空时，AutoCAD 拒绝从任意目录加载托管程序集；
放进安装目录（天然受信任）后立即可用。

```bash
python tools/netload.py --deploy     # 复制到安装目录 + 写注册表（幂等）
python tools/netload.py              # 再启动 AutoCAD 跑 4 条命令并按读回验收
python tools/netload.py --undeploy   # 清干净（注册表键 + 安装目录副本 + 旧 bundle）
```

> 部署要在 AutoCAD **关闭**时执行（DLL 被占用会 `PermissionError`）。
> 加载只在 AutoCAD **启动时**发生，已在运行的实例需重启。

## 设计约定

每条命令把结果写成图面上一行 MText：

```
AKRESULT <TAG>: <key>=<value> ...
```

这样验证走 acadkit 既有的**读回**通道（`judges/read.py`），不解析命令行文本、不信任返回值；
`judges/netchannel.py` 的判据还对关键量做独立复核（例如 `solid.revolve` 直接比
`3DSOLID.Volume` 与 π(R²−r²)h，`layer.state` 直接读图层颜色）。

## 依赖边界

本目录**不复制**任何 Autodesk 二进制；构建时从 `$(AcadDir)` 引用，产物只有我们自己的 DLL。
`.gitignore` 已排除 `bin/`、`obj/`。
