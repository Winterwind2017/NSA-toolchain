#!/usr/bin/env python3
"""生成 `docs/UNSUPPORTED.md`（从 registry 的 dead / external 两张表）。

    python tools/gen_unsupported.py          # 写文件
    python tools/gen_unsupported.py --check  # 只检查（pre-push 用）

排版固定，内容全部来自 `docs/registry.yaml`；散文部分在下面的 `PROSE_*`
常量里，改这里、不要手改生成的文件。
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import registry          # noqa: E402

OUT = os.path.join(ROOT, "docs", "UNSUPPORTED.md")

PROSE_HEAD = """# 用不了的能力（按"卡在哪里"分类）

> 本文件由 `python tools/gen_unsupported.py` 从 `docs/registry.yaml` 生成。
> **不要手改**：改 registry 的 `status`/`judge`/`evidence`，再重新生成。

这个仓库的原则：**说不清判据的能力不许标 verified**。用不了的也写清楚——
是"本机没有官方路径"，还是"依赖外部资产"，还是"能跑但结果不可信"。
"""

PROSE_MEASURED = """
## 看着能用、其实不能用的坑（实测）

这些不是 registry 里的某条能力，而是做能力时踩到的"调用成功但结果不对"，
写在这里防止后来者再信返回值：

| 现象 | 实测 | 结论 |
|---|---|---|
| `Solid3D.Boolean(1, other)` 并集 | 两个 8000 的盒子（重叠 2000）算出 **4000**；`Boolean(3, …)` 报"参数 Operation 无效" | ActiveX 布尔不可用，改走命令行 `_.UNION/SUBTRACT/INTERSECT`（按句柄选择） |
| `Plot.PlotToFile` | 返回 True，文件 **0 字节**（默认 `BACKGROUNDPLOT=2`，要等文档关闭才落盘） | 出图前临时置 `BACKGROUNDPLOT=0`，用完还原并读回校验 |
| `MLeader.TextString` | 赋值不报错、读回**空串** | 序号气泡改用圆 + 引线 + 文字拼 |
| `-LAYERSTATE` | 只要动过图层表（COM 建层 / entmake / SaveAs 之后），Save **永久卡在命令提示符**；`SendCommand`、LISP `command`、`vl-cmdf` 全试过 | **已用 .NET 通道解决**：`layer.state` 走 `LayerStateManager`（进程内），见 `dotnet/`。ActiveX 侧仍不可用，故保留本条 |
| `(command "…")` in `SendCommand` | 双文档（基线 + 用例）下偶发挂起 | 改用 `(vl-cmdf "…")`（非交互），并给每例加看门狗 |
| `_.NETLOAD`（命令行 / `vl-cmdf`） | **弹模态文件对话框，SendCommand 永久阻塞**（FILEDIA=0 无效） | 不要用 NETLOAD。改注册表 `LOADCTRLS=2` + 把 DLL 放进 **AutoCAD 安装目录**（`SECURELOAD=1` 会拒绝未信任路径） |
| Autoloader bundle | bundle 放进 `%APPDATA%\Autodesk\ApplicationPlugins\` 后命令仍"未知命令" | 同上，走安装目录 + 注册表；`tools/netload.py --deploy` 已封装 |
| `AddRevolvedSolid` | XY 矩形 / 圆 / 3D 多段线三种轮廓都报"输入无效"；命令行 `_.REVOLVE` 也没生成实体 | **已用 .NET 通道解决**：`solid.revolve` 走进程内 `Solid3d.CreateRevolvedSolid`，实测体积误差 0.0；ActiveX 侧仍不可用 |
| `LWPOLYLINE.NumberOfVertices` | 只有旧 `POLYLINE` 有这个属性 | 顶点用 `Coordinates` 的坐标对读 |
| 标注 `TextPosition` | 传 (30,10) 读回 (30,11.875)（自动避让） | 只判"文字在尺寸线哪一侧"，不判相等 |
| `ACDBTABLE` 第 0 行 | 是**合并标题行**，往它的第 1..n 列 `SetText`：内存读得到、落盘重开变空串（ASCII 也一样） | 表头放第 1 行，BOM 用 5 行排法 |
"""

PROSE_TAIL = """
## 复核触发条件

上面这些结论都带"本机 + 版本"的前提（AutoCAD 2025 / R25.0 / `<<VANILLA>>`）。
出现以下情况时要重新测，不要直接沿用：

1. 换 AutoCAD 版本（R26+）或换机器；
2. Autodesk 更新了 ActiveX 类型库（`acdbmgd`/`acad` 的 COM 接口）；
3. 判据在某台机器上突然失败，而代码没改——先怀疑环境，再怀疑能力。

复核方法：`python tests/live_judges.py --only <族>`，看 `_scratch/.../progress.txt`
与 `results.json` 的 `detail/raw`。
"""


def render() -> str:
    data = registry.load()
    dead = [c for c in data["capabilities"] if c.get("status") == "dead"]
    ext = [c for c in data["capabilities"] if c.get("status") == "external"]
    lines = [PROSE_HEAD, ""]
    lines += ["## dead（本机没有可用的官方路径）", "",
              "| 能力 | 族 | 卡在哪里 / 替代方案 | 证据 |",
              "|---|---|---|---|"]
    for c in sorted(dead, key=lambda x: x["id"]):
        lines.append("| `%s` | %s | %s | %s |"
                     % (c["id"], c.get("family", ""),
                        str(c.get("judge", "")).replace("|", "/"),
                        str(c.get("evidence", ""))))
    lines += ["", "## external（不属于本内核的交付范围）", "",
              "| 能力 | 族 | 为什么 | 证据 |",
              "|---|---|---|---|"]
    if not ext:
        lines.append("| — | — | 当前没有 external：原来的 4 条（Electrical 库 / PLC / "
                     "P&ID / 投影）已在 2026-10-21 的接口挖掘里转成 verified，"
                     "见 `CAPABILITIES.md` | — |")
    for c in sorted(ext, key=lambda x: x["id"]):
        lines.append("| `%s` | %s | %s | %s |"
                     % (c["id"], c.get("family", ""),
                        str(c.get("judge", "")).replace("|", "/"),
                        str(c.get("evidence", ""))))
    lines += [PROSE_MEASURED, PROSE_TAIL]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 docs/UNSUPPORTED.md")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        if not os.path.isfile(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("docs/UNSUPPORTED.md 过期：跑 `python tools/gen_unsupported.py`")
            return 1
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("已写 %s" % os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
