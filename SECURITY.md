# 安全策略

## 报告漏洞

**不要开公开 issue。** 请用 GitHub 的 [私密漏洞报告](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
（Security → Report a vulnerability），或直接联系仓库所有者。

请在报告里给出：影响范围、复现步骤、版本/提交、是否已在真机验证。

## 本项目的安全模型

- **本地优先**：hub 是 stdio 进程，只驱动本机已安装的软件；不上传图纸、不访问网络服务。
- **权限等同当前用户**：工具会以你的身份执行 COM/UIAutomation/CLI 调用，能力上限 = 你的桌面会话权限。
- **会真实改文件**：存盘、导出、编译、写工程。调用前请确认有备份/版本控制。
- **不提供许可证绕过**：所有真机能力都通过软件官方接口，不修改、不破解其授权机制。

## 使用建议

1. 在专用工作目录里跑，不要直接指向生产图纸目录。
2. 对"会覆盖原文件"的操作（`save` / `export` / `compile` / `apply`），先在副本上验证。
3. MCP 客户端配置里使用**绝对路径**，避免在不同目录启动时加载到别的包。
4. 不要把 `%USERPROFILE%\.dsh`、`config.toml`、凭据文件提交进仓库。
5. 仓库里的 `_runs/`、`_archive/` 是运行产物，已在 `.gitignore` 中排除；不要 force-add。

## 支持范围

| 版本 | 安全修复 |
|---|---|
| 最新 `main` | ✅ |
| 最近一个 tag | ✅（尽力） |
| 更早版本 | ❌ |

只有本仓库自身的代码在范围内。第三方软件（AutoCAD/SolidWorks/NX/...）的漏洞请报给对应厂商。
