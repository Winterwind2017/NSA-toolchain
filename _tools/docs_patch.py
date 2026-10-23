"""文档补丁：PITFALLS 37-38、UNSUPPORTED 一行、STATUS 的 apply 段落。"""

import pathlib

ROOT = pathlib.Path(r"D:\bililive\gxkit\docs")

# --- PITFALLS ---
p = ROOT / "PITFALLS.md"
t = p.read_text(encoding="utf-8").rstrip("\n")
add = """

## 三十七、XML 骨架不要"每次运行时去读 MELSOFT 的样例"

早期 `xmlgen` 每次生成都以安装目录里的 `Sample.xml` 当骨架——MELSOFT 一升级换样例，
整套生成器就可能整批失效，而且**失效方式是静默的**。

现在：首次运行把样例复制到 `%LOCALAPPDATA%/gxkit/skeleton.xml` 并记下 sha256，
之后都读缓存；指纹变了自动重建；`GXKIT_TEMPLATE=<文件>` 可以完全绕开安装目录。

## 三十八、手写骨架卡在"局部标签"

我们自己写的 `templates/base.xml`（`use_manual_template()` 可切）能让
程序、全局标签、全局结构体+成员名访问全部导入成功；但**局部标签不落地**
（locals_found=0，随后 `程序(...)转换中` 报 2 错）。

排除过的因素：`PouProperties title`、`AddData` 内部顺序、去掉 `VariableRemark`/
`InitialValue`、补 `BodyProperties`/`FbPouProperties`。FB 那条因此通了，局部标签没有。
要真正自给自足，得继续做"逐元素 diff 二分"，记在 `docs/EXPAND_BACKLOG.md` 第 6 条。
"""
p.write_text(t + add + "\n", encoding="utf-8")
print("PITFALLS ok")

# --- UNSUPPORTED ---
p = ROOT / "UNSUPPORTED.md"
t = p.read_text(encoding="utf-8").rstrip("\n")
row = ("| `xmlgen.self_contained_template`（完全不用 MELSOFT 样例的骨架） | 手写骨架能导入程序/标签/"
       "全局结构体，但**局部标签不落地**（locals_found=0 + 转换 2 错）；已排除 title/顺序/"
       "Remark/InitialValue/BodyProperties 五个因素 | 探针 79 + tc1-tt3 |")
if "self_contained_template" not in t:
    t = t + "\n" + row + "\n"
p.write_text(t, encoding="utf-8")
print("UNSUPPORTED ok")

# --- STATUS ---
p = ROOT / "STATUS.md"
t = p.read_text(encoding="utf-8")
t = t.replace(
    "真机通过能力：**25** 条（其中 23 条已全量连跑两次通过；`inspect.programs` / `project.diff` 单项通过，**全量复跑待补**）",
    "真机通过能力：**25** 条")
apply_section = """## 一条命令干活

```powershell
python -m gxkit apply --xml build.xml --dry        # 只做离线预检（不开 GX Works3）
python -m gxkit apply --xml build.xml              # 导入 -> 编译 -> 存盘 -> 报告
```

`apply` 会打印并写出 `apply_report.json`：程序/功能块/结构体/标签清单、导入是否生效、
源码块数、步数、编译错误、失败阶段。退出码 0 = 可交付。

## 复现"""
if "## 一条命令干活" not in t:
    t = t.replace("## 复现", apply_section, 1)
p.write_text(t, encoding="utf-8")
print("STATUS ok")
