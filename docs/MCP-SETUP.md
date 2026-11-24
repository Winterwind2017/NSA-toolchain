# 把 hub 接进 MCP 客户端

hub 是标准 **stdio MCP server**，一个端点聚合 9 个 kit（AutoCAD / SolidWorks / NX / GX Works3 /
CODESYS / AutoShop / CATIA / EPLAN / UG）。

## 一、启动命令（三选一）

### 1) 直接用模块（跨平台，推荐）

```bash
PYTHONPATH=/path/to/NSA-toolchain/hub python -m nsa_mcp_hub.servers.nsa_hub_mcp
```

### 2) Windows 启动器（仓库自带，无写死路径）

```
D:\path\to\NSA-toolchain\hub\_tools\nsa-mcp-hub.cmd
```

只挂单个内核时用 `nsa-mcp-hub-acad.cmd` / `-sw` / `-nx` / `-gx` / `-codesys` / `-autoshop` / `-eplan`，
启动器数量少、暴露的工具面也小（例如 acad 是 54 个工具，聚合是 600+）。

### 3) 装成命令（可选）

```bash
pip install -e hub
nsa-hub          # 见 hub/pyproject.toml [project.scripts]
```

## 二、各客户端配置

### Claude Desktop（`claude_desktop_config.json`）

```json
{
  "mcpServers": {
    "nsa-hub": {
      "command": "python",
      "args": ["-m", "nsa_mcp_hub.servers.nsa_hub_mcp"],
      "env": { "PYTHONPATH": "D:/path/to/NSA-toolchain/hub", "PYTHONIOENCODING": "utf-8" }
    }
  }
}
```

### Cursor（`.cursor/mcp.json`）

```json
{
  "mcpServers": {
    "nsa-hub": {
      "command": "cmd",
      "args": ["/c", "D:/path/to/NSA-toolchain/hub/_tools/nsa-mcp-hub.cmd"]
    }
  }
}
```

### Codex（`~/.codex/config.toml`）

```toml
[mcp_servers.nsa_hub]
command = 'python'
args = ['-m', 'nsa_mcp_hub.servers.nsa_hub_mcp']
env = { PYTHONPATH = 'D:\path\to\NSA-toolchain\hub', PYTHONIOENCODING = 'utf-8' }
startup_timeout_sec = 120
```

### DeepSeek Harness（`~/.dsh/cordis.patch.yml`）

```yaml
- id: nsa-mcp-hub
  name: "@deepseek-ai/dsh-mcp-client"
  config:
    serverName: nsa-mcp-hub
    transport: stdio
    command: C:\Windows\System32\cmd.exe
    args:
      - /c
      - D:\path\to\NSA-toolchain\hub\_tools\nsa-mcp-hub.cmd
```

## 三、验证接好了

在客户端里调用内置工具 `nsa_hub_status`，应返回：

```json
{"hub": "nsa-mcp-hub", "kits_total": 9, "kits_alive": 9, "tools_total": 638}
```

`kits_alive` 取决于你装了哪些软件：没装 CAD 时对应 kit 是 `alive: false`，属正常。

## 四、常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `kits_alive: 0` | 启动时没拉起任何 kit | 先单独跑 `PYTHONPATH=hub python -m nsa_mcp_hub.servers.nsa_hub_mcp`，看 stderr |
| 工具调用返回 `ok:false` 且 `errors` 有 COM 报错 | 软件没开 / 没登录桌面会话 | 用**同一个用户**在交互式桌面登录并打开软件 |
| 找不到 `python` | MCP 客户端 PATH 与你 shell 不同 | 用绝对路径，或设 `NSA_PYTHON` |
| 中文乱码 | 终端编码 | 设 `PYTHONIOENCODING=utf-8`（启动器已设） |
| 启动超时 | 首个 kit 冷启动慢（CODESYS 约 10 s） | 客户端 `startup_timeout_sec` 调到 120 |

## 五、安全边界

- hub 只通过官方自动化接口驱动**本机已安装**的软件；不联网、不上传图纸。
- 工具会真实改文件（存盘、导出、编译）。调用前请确保工程已保存/可回退。
- 建议在专用工作目录里跑，不要把客户图纸直接指向生产目录。
