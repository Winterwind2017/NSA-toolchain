"""生成"只有全局标签"的 IEC 61131-10 XML —— 以官方 Sample.xml 为骨架。

为什么不用从零拼的最小文档：实测从零拼的 `<GlobalVars>` **会被静默忽略**
（导入成功、`Progress.txt` 里连"全局标签(Global1)定义检查中"这一步都不出现）。

实测踩出来的四条：
  1. `GlobalVars` 必须放在 `Project/Instances/Configuration/` 下；
     放 `Types/GlobalNamespace` 下、或 `Instances/` 下少一层 `Configuration`，都会被忽略。
  2. 变量要**克隆样例里的整条 `<Variable>`**（含它的 AddData 结构），不要自己拼最小变量。
  3. 克隆后必须把 `<VariableLineNumber>` 改成**唯一**编号，注释/备注也换成各自的，
     否则三个变量只会进第一个（实测 rows 只 +7，只出现 LBL_A）。
  4. 改完这三处，3 个标签全部落地（rows 54 → 75，含注释与备注）。
"""

from __future__ import annotations

import copy
import pathlib
import xml.etree.ElementTree as ET

NS = "www.iec.ch/public/TC65SC65BWG7TF10"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
SAMPLE = pathlib.Path(
    r"D:\Program Files (x86)\MELSOFT\GPPW3\SampleData\IEC61131-10XML\Sample.xml")

ET.register_namespace("", NS)
ET.register_namespace("xsi", XSI)


def _q(tag: str) -> str:
    return "{%s}%s" % (NS, tag)


DEFAULT_LABELS = [
    {"name": "LBL_A", "type": "BOOL", "address": "M50", "comment": "gxkit A"},
    {"name": "LBL_B", "type": "BOOL", "address": "M51", "comment": "gxkit B"},
    {"name": "LBL_C", "type": "BOOL", "address": "M52", "comment": "gxkit C"},
]


def build(labels: list[dict] | None = None,
          sample: str | pathlib.Path = SAMPLE) -> ET.ElementTree:
    labels = labels or DEFAULT_LABELS
    tree = ET.parse(str(sample))
    root = tree.getroot()

    # 1) Types：只留 Documentation + AddData（去掉程序/FB/FUN/结构体）
    gn = root.find(_q("Types")).find(_q("GlobalNamespace"))
    for ch in list(gn):
        if ch.tag.replace("{%s}" % NS, "") not in ("Documentation", "AddData"):
            gn.remove(ch)

    # 2) Instances/Configuration：只留一张 GlobalVars 表
    cfg = root.find(_q("Instances")).find(_q("Configuration"))
    for ch in list(cfg):
        if ch.tag != _q("GlobalVars"):
            cfg.remove(ch)
    tables = cfg.findall(_q("GlobalVars"))
    for extra in tables[1:]:
        cfg.remove(extra)
    gv = tables[0] if tables else ET.SubElement(
        cfg, _q("GlobalVars"), {"constant": "false", "retain": "false"})

    # 3) 克隆样例里第一条 Variable 当模板，逐个改名/改址/改唯一编号
    old_vars = gv.findall(_q("Variable"))
    if not old_vars:
        raise RuntimeError("样例里没有可克隆的 Variable")
    template = copy.deepcopy(old_vars[0])
    for var in old_vars:
        gv.remove(var)

    for idx, item in enumerate(labels, start=1):
        var = copy.deepcopy(template)
        var.set("name", item["name"])
        for ln in var.iter(_q("VariableLineNumber")):
            ln.set("number", str(idx))
        for ct in var.iter(_q("CommentText")):
            ct.text = item.get("comment") or item["name"]
        for rt in var.iter(_q("RemarkText")):
            rt.text = item.get("remark") or (item["name"] + " remark")
        for tn in var.iter(_q("TypeName")):
            tn.text = item.get("type", "BOOL")
        ad = var.find(_q("Address"))
        if ad is not None and item.get("address"):
            ad.set("address", item["address"])
        gv.append(var)

    ET.indent(tree, space="\t")
    return tree


def write(path: str | pathlib.Path, labels: list[dict] | None = None,
          sample: str | pathlib.Path = SAMPLE) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    build(labels, sample).write(p, encoding="utf-8", xml_declaration=True)
    return p


if __name__ == "__main__":
    out = write(pathlib.Path(r"D:\bililive\gxkit\_runs\labels\labels.xml"))
    print("written:", out, out.stat().st_size)
