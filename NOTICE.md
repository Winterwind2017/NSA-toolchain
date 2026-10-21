# NOTICE

本仓库是**独立实现的 AutoCAD 自动化内核**（`acadkit`），不包含 Autodesk 的
任何代码或文档副本。

## 第三方依赖

| 依赖 | 许可 | 用途 |
|---|---|---|
| [pywin32](https://github.com/mhammond/pywin32) | PSF-2.0 | 晚绑定 COM（生产依赖） |
| [ezdxf](https://github.com/mozman/ezdxf) | MIT | DXF 读回判据（可选，`acadkit[dxf]`） |
| [pypdf](https://github.com/py-pdf/pypdf) | BSD-3-Clause | 多页 PDF 合并（可选，`acadkit[pdf]`） |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | MIT | MCP server（可选，`acadkit[mcp]`） |
| [pytest](https://github.com/pytest-dev/pytest) | MIT | 测试（`dev`） |

## 与 Autodesk 的关系

- 本仓库**不隶属于** Autodesk，也未获其背书。
- "AutoCAD" 是 Autodesk, Inc. 的商标，此处仅用于说明软件兼容性。
- 仓库里没有分发 AutoCAD 的任何二进制、帮助文档（`.chm`）或 ActiveX
  类型库（`.tlb`）；运行时通过用户本机安装的 AutoCAD 的 COM 接口调用。
- 判据里引用的 API 名称（如 `AddDimRotated`）来自公开的 ActiveX 文档与
  本机实测，未复制文档正文。

## 实测证据的来源

`docs/` 里的数字（体积、面积、页数、时间）全部来自本机 AutoCAD 2025 +
`<<VANILLA>>` 配置的实测记录；`docs/regression/` 下的 JSON 是原始证据，
未做手改。

