# NOTICE —— 第三方代码与商标声明

本仓库采用 MIT 许可（见 `LICENSE`）。下列第三方作品的知识产权归其各自作者所有。

## 1. Solidworks-MCP-Server（工具目录结构的来源）

- 项目：Solidworks-MCP-Server
- 作者：Eduardo Font Cruz
- 来源：https://github.com/Eduardof0nt/Solidworks-MCP-Server
- 许可：MIT（Copyright (c) 2026 Eduardo Font Cruz）
- 本仓库如何使用：参考了其 188 个工具的分组与命名思路；`src/swkit/registry.py`
  沿用了同名工具名以便迁移。**其实现未经原样复制**——本仓库的实现以内核 API 与实测配方重写，
  且明确标注了上游若干实现调用的是类型库中不存在的方法（见 `docs/UNSUPPORTED.md`）。

## 2. cad_framework（SolidWorksApp 高层 API 的来源）

- 项目：Non-standard-automation-design
- 作者：Winterwind2017（本仓库作者本人）
- 许可：MIT
- 本仓库如何使用：`src/swkit/api/app.py`、`src/swkit/core/base.py`、
  `src/swkit/core/errors.py`、`src/swkit/api/advanced.py` 由该项目移植，接口保持兼容。

## 3. 商标

SOLIDWORKS® 是 Dassault Systèmes SolidWorks Corporation 的注册商标。
本项目为个人项目，**与 Dassault Systèmes 无关联、未获其背书**。
