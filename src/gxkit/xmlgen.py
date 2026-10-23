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

# 每种类型的默认初值：初值类型必须与变量类型对得上，否则标签只落一部分/不落
TYPE_DEFAULTS = {
    "BOOL": ("FALSE", "M"),
    "WORD": ("0", "W"),
    "DWORD": ("0", "D"),
    "INT": ("0", "W"),
    "DINT": ("0", "D"),
    "REAL": ("0.0", "D"),
}


def _fix_initial_value(var, value: str) -> None:
    """把 `<InitialValue><SimpleValue value=...>` 设成与类型匹配的值（没有就补一个）。"""
    iv = var.find(_q("InitialValue"))
    if iv is None:
        iv = ET.SubElement(var, _q("InitialValue"))
    simples = list(iv.iter(_q("SimpleValue")))
    if simples:
        for sp in simples:
            sp.set("value", value)
    else:
        ET.SubElement(iv, _q("SimpleValue"), {"value": value})


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
        _ensure_line_number(var, idx)
        for ct in var.iter(_q("CommentText")):
            ct.text = item.get("comment") or item["name"]
        for rt in var.iter(_q("RemarkText")):
            rt.text = item.get("remark") or (item["name"] + " remark")
        for tn in var.iter(_q("TypeName")):
            tn.text = item.get("type", "BOOL")
        kind = item.get("type", "BOOL")
        default_init, default_dev = TYPE_DEFAULTS.get(kind, ("0", "W"))
        _fix_initial_value(var, item.get("init", default_init))
        ad = var.find(_q("Address"))
        if ad is not None and item.get("address"):
            ad.set("address", item["address"])
        elif ad is not None and item.get("address") is None:
            # 非 BOOL 默认给一个该类型的地址（不给自己也能过，但给上更接近真实工程）
            var.remove(ad)
        gv.append(var)

    ET.indent(tree, space="\t")
    return tree


def write(path: str | pathlib.Path, labels: list[dict] | None = None,
          sample: str | pathlib.Path = SAMPLE) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    build(labels, sample).write(p, encoding="utf-8", xml_declaration=True)
    return p


def build_program(program_name: str, st_code: str,
                  locals_: list[dict] | None = None,
                  sample: str | pathlib.Path = SAMPLE) -> ET.ElementTree:
    """用样例骨架造一个"只有 ST 程序"的文档，用来让 GX Works3 **建出新程序**。

    实测要点（缺一条就不建程序）：
      * `Types/GlobalNamespace/Program` 保留样例的结构（Documentation/AddData/MainBody），
        但**删掉全部 `<Vars>`** —— 否则会引用 FBPou1/Struct1/TIMER 等不存在的类型；
      * `Instances/Configuration/Resource` 里要有
        `<ProgramInstance name="<同名>" typeName="pou" evaluationOrder="1"/>`，
        程序名两边必须一致；
      * `MainBody` 只留一个 `BodyContent xsi:type="ST"`，正文用设备软元件（B0/W0），
        不要引用局部标签。
    """
    tree = ET.parse(str(sample))
    root = tree.getroot()
    gn = root.find(_q("Types")).find(_q("GlobalNamespace"))

    src_prog = next(p for p in gn.findall(_q("Program")) if p.get("name") == "Program1")
    prog = copy.deepcopy(src_prog)
    for ch in list(gn):
        if ch.tag == _q("Program") or ch.tag in (
                _q("FunctionBlock"), _q("Function"), _q("DataTypeDecl")):
            gn.remove(ch)

    prog.set("name", program_name)
    vars_tpl = prog.findall(_q("Vars"))
    for vars_el in list(vars_tpl):
        prog.remove(vars_el)
    if locals_ and vars_tpl:
        # 局部标签：必须在 MainBody 之前（XSD 顺序），每个变量带唯一行号
        body_pos = list(prog).index(prog.find(_q("MainBody")))
        prog.insert(body_pos, _make_vars(vars_tpl[0], locals_, start_line=1))
    body = prog.find(_q("MainBody"))
    if body is None:
        body = ET.SubElement(prog, _q("MainBody"))
    bcs = body.findall(_q("BodyContent"))
    for extra in bcs[1:]:
        body.remove(extra)
    if bcs:
        bcs[0].find(_q("ST")).text = st_code
    else:
        bc = ET.SubElement(body, _q("BodyContent"), {"{%s}type" % XSI: "ST"})
        ET.SubElement(bc, _q("ST")).text = st_code
    gn.append(prog)

    cfg = root.find(_q("Instances")).find(_q("Configuration"))
    res_src = next(r for r in cfg.findall(_q("Resource")) if r.get("name") == "Main")
    for ch in list(cfg):
        cfg.remove(ch)
    res = copy.deepcopy(res_src)
    for ch in list(res):
        if ch.tag != _q("ProgramInstance"):
            res.remove(ch)
    inst = res.find(_q("ProgramInstance"))
    inst.set("name", program_name)
    inst.set("typeName", "pou")
    inst.set("evaluationOrder", "1")
    cfg.append(res)

    ET.indent(tree, space="\t")
    return tree


def write_program(path: str | pathlib.Path, program_name: str, st_code: str,
                  locals_: list[dict] | None = None,
                  sample: str | pathlib.Path = SAMPLE) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    build_program(program_name, st_code, locals_=locals_, sample=sample).write(
        p, encoding="utf-8", xml_declaration=True)
    return p


DEFAULT_LOCALS = [
    {"name": "LocBool", "type": "BOOL", "init": "FALSE"},
    {"name": "LocWord", "type": "WORD", "init": "0"},
]

DEFAULT_FB_LOCALS = [
    {"name": "FB_Bool", "type": "BOOL", "init": "FALSE"},
    {"name": "FB_Word", "type": "WORD", "init": "0"},
]


ADD_NS = "http://www.mitsubishielectric.com/xml/"


def _ensure_line_number(var, number: int) -> None:
    """保证变量带唯一的 <VariableLineNumber>；没有就补一个。

    功能块的样例变量只带 VariableComments，没有行号——补上更稳（也便于测试断言）。
    """
    found = list(var.iter(_q("VariableLineNumber")))
    if found:
        for ln in found:
            ln.set("number", str(number))
        return
    data_name = ADD_NS + "VariableLineNumber"
    add = var.find(_q("AddData"))
    if add is None:
        add = ET.Element(_q("AddData"))
        type_el = var.find(_q("Type"))
        idx = list(var).index(type_el) if type_el is not None else len(var)
        var.insert(idx, add)
    data = ET.SubElement(add, _q("Data"),
                         {"name": data_name, "handleUnknown": "implementation"})
    ET.SubElement(data, _q("VariableLineNumber"), {"number": str(number)})


def _make_vars(template_vars, items: list[dict], tag: str = "Vars",
               start_line: int = 1):
    """克隆样例的 `<Vars>` 容器与 `<Variable>`，换成我们的名字/类型/唯一行号。"""
    tpl_var = template_vars.find(_q("Variable"))
    if tpl_var is None:
        raise RuntimeError("样例里没有可克隆的 Variable")
    vars_el = copy.deepcopy(template_vars)
    for old in vars_el.findall(_q("Variable")):
        vars_el.remove(old)
    for idx, item in enumerate(items, start=start_line):
        var = copy.deepcopy(tpl_var)
        var.set("name", item["name"])
        _ensure_line_number(var, idx)
        for ct in var.iter(_q("CommentText")):
            ct.text = item.get("comment") or item["name"]
        for rt in var.iter(_q("RemarkText")):
            rt.text = item.get("remark") or (item["name"] + " remark")
        for tn in var.iter(_q("TypeName")):
            tn.text = item.get("type", "BOOL")
        sv = var.find(_q("InitialValue"))
        if sv is not None and item.get("init") is not None:
            for simple in sv.iter(_q("SimpleValue")):
                simple.set("value", item["init"])
        vars_el.append(var)
    return vars_el


def build_fb_program(program_name: str, st_code: str,
                     fb_name: str = "FBGen",
                     fb_body: str = "FB_Bool := NOT FB_Bool;\r\nFB_Word := FB_Word + 1;",
                     locals_: list[dict] | None = None,
                     fb_locals: list[dict] | None = None,
                     sample: str | pathlib.Path = SAMPLE) -> ET.ElementTree:
    """建一套"带局部标签的程序 + 一个功能块"的 XML。

    实测出来的必要条件（每条都是**静默**失败——导入"成功"、工程里什么都没有）：

      1. **顺序**：`Program` 必须在 `FunctionBlock` **之前**。
         （把 FB 插到 Program 前面时，整份文档被忽略，连程序都不建。）
      2. 功能块要**删掉 `<Parameters>`**：它声明 Inout/Input/Output 并引用样例里的
         `fb1_*` 变量，留着会让整份导入失效。
      3. 功能块的 `<Vars>` 只留**一块**（private），换自己的变量；
         每块里每个 `<Variable>` 的 `VariableLineNumber` 必须唯一。
      4. `Instances/Configuration/Resource/ProgramInstance` **只给程序**，功能块不是实例。
      5. 变量类型只用基础类型（BOOL/WORD/INT…）；引用不存在的 FB/结构体同样会失败。
    """
    locals_ = locals_ or DEFAULT_LOCALS
    fb_locals = fb_locals or DEFAULT_FB_LOCALS

    tree = ET.parse(str(sample))
    root = tree.getroot()
    gn = root.find(_q("Types")).find(_q("GlobalNamespace"))

    # 只留 Documentation + AddData，其它类型/程序全部重建
    for ch in list(gn):
        if ch.tag.replace("{%s}" % NS, "") not in ("Documentation", "AddData"):
            gn.remove(ch)

    src_root = ET.parse(str(sample)).getroot()
    src_gn = src_root.find(_q("Types")).find(_q("GlobalNamespace"))
    src_prog = next(p for p in src_gn.findall(_q("Program")) if p.get("name") == "Program1")
    src_fb = next(f for f in src_gn.findall(_q("FunctionBlock"))
                  if f.get("name") == "FBPou1")

    # ---- 程序（带局部标签）----
    prog = copy.deepcopy(src_prog)
    prog.set("name", program_name)
    prog_vars_tpl = prog.findall(_q("Vars"))[0]
    for old in prog.findall(_q("Vars")):
        prog.remove(old)
    # Vars 必须插在 MainBody 之前（XSD 顺序）
    body_pos = list(prog).index(prog.find(_q("MainBody")))
    prog.insert(body_pos, _make_vars(prog_vars_tpl, locals_, start_line=1))
    body = prog.find(_q("MainBody"))
    bcs = body.findall(_q("BodyContent"))
    for extra in bcs[1:]:
        body.remove(extra)
    if bcs:
        bcs[0].find(_q("ST")).text = st_code
    else:
        bc = ET.SubElement(body, _q("BodyContent"), {"{%s}type" % XSI: "ST"})
        ET.SubElement(bc, _q("ST")).text = st_code
    gn.append(prog)          # ← 先程序

    # ---- 功能块（在程序之后）----
    fb = copy.deepcopy(src_fb)
    fb.set("name", fb_name)
    for ch in list(fb):                       # ① 去掉 Parameters
        if ch.tag == _q("Parameters"):
            fb.remove(ch)
    fb_vars_blocks = fb.findall(_q("Vars"))
    fb_vars_tpl = fb_vars_blocks[0]
    for v in fb_vars_blocks:                  # ② Vars 只留一块
        fb.remove(v)
    fb_body_el = fb.find(_q("MainBody"))
    fb.insert(list(fb).index(fb_body_el),
              _make_vars(fb_vars_tpl, fb_locals, start_line=1))
    fb_bcs = fb_body_el.findall(_q("BodyContent"))
    for extra in fb_bcs[1:]:
        fb_body_el.remove(extra)
    if fb_bcs:
        fb_bcs[0].find(_q("ST")).text = fb_body
    else:
        bc = ET.SubElement(fb_body_el, _q("BodyContent"), {"{%s}type" % XSI: "ST"})
        ET.SubElement(bc, _q("ST")).text = fb_body
    gn.append(fb)            # ← 后功能块

    # ---- 实例：只给程序 ----
    cfg = root.find(_q("Instances")).find(_q("Configuration"))
    res_src = next(r for r in cfg.findall(_q("Resource")) if r.get("name") == "Main")
    for ch in list(cfg):
        cfg.remove(ch)
    res = copy.deepcopy(res_src)
    for ch in list(res):
        if ch.tag != _q("ProgramInstance"):
            res.remove(ch)
    inst = res.find(_q("ProgramInstance"))
    inst.set("name", program_name)
    inst.set("typeName", "pou")
    inst.set("evaluationOrder", "1")
    cfg.append(res)

    ET.indent(tree, space="\t")
    return tree


def write_fb_program(path: str | pathlib.Path, program_name: str, st_code: str,
                     fb_name: str = "FBGen", fb_body: str | None = None,
                     locals_: list[dict] | None = None,
                     fb_locals: list[dict] | None = None,
                     sample: str | pathlib.Path = SAMPLE) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {}
    if fb_body is not None:
        kwargs["fb_body"] = fb_body
    build_fb_program(program_name, st_code, fb_name=fb_name,
                     locals_=locals_, fb_locals=fb_locals,
                     sample=sample, **kwargs).write(
        p, encoding="utf-8", xml_declaration=True)
    return p


if __name__ == "__main__":
    out = write(pathlib.Path(r"D:\bililive\gxkit\_runs\labels\labels.xml"))
    print("written:", out, out.stat().st_size)


DEFAULT_STRUCT_MEMBERS = [
    {"name": "M_Bool", "type": "BOOL", "init": "FALSE"},
    {"name": "M_Word", "type": "WORD", "init": "0"},
]


def build_struct_program(program_name: str, st_code: str,
                         struct_name: str = "StructGen",
                         members: list[dict] | None = None,
                         locals_: list[dict] | None = None,
                         sample: str | pathlib.Path = SAMPLE) -> ET.ElementTree:
    """建"结构体 + 用它的程序"的 XML。

    结构体形态照抄样例 `Struct1`：
        DataTypeDecl[@name]
          Documentation
          AddData/DataTypeProperties
          UserDefinedTypeSpec[@type="StructTypeSpec"]
            Member[@name] × N   （每个 Member 带 Type/TypeName，可选 InitialValue）
    顺序：`Program` 在前，`DataTypeDecl` 在后（和 FunctionBlock 一样，类型必须在程序之后）。
    """
    # members=None 表示"保留样例成员原样"——删/改成员会让整份导入被丢弃（实测）
    locals_ = locals_ or DEFAULT_LOCALS

    tree = build_program(program_name, st_code, locals_=locals_, sample=sample)
    root = tree.getroot()
    gn = root.find(_q("Types")).find(_q("GlobalNamespace"))

    src_gn = ET.parse(str(sample)).getroot().find(_q("Types")).find(_q("GlobalNamespace"))
    src_struct = next(d for d in src_gn.findall(_q("DataTypeDecl"))
                      if d.get("name") == "Struct1")
    tpl_member = src_struct.find(_q("UserDefinedTypeSpec")).find(_q("Member"))

    st_el = copy.deepcopy(src_struct)
    st_el.set("name", struct_name)
    spec = st_el.find(_q("UserDefinedTypeSpec"))
    if members is not None:
        _replace_members(spec, members, tpl_member)
    gn.append(st_el)          # ← 类型放在程序之后
    ET.indent(tree, space="\t")
    return tree


def _replace_members(spec, members: list[dict], tpl_member,
                     start_no: int = 1) -> None:
    """替换 `UserDefinedTypeSpec` 里的 `<Member>`，**保持它的 `<AddData>` 在最后**。

    这一条是踩出来的：`<AddData>` 若跑到 Member 前面，整份导入会被静默丢弃
    （探针 73 的四个候选全灭，最后是靠结构对比发现顺序反了）。
    """
    add_blocks = [ch for ch in list(spec) if ch.tag == _q("AddData")]
    for old in spec.findall(_q("Member")):
        spec.remove(old)
    insert_at = list(spec).index(add_blocks[0]) if add_blocks else len(spec)
    for offset, item in enumerate(members):
        mem = copy.deepcopy(tpl_member)
        mem.set("name", item["name"])
        for ln in mem.iter(_q("VariableLineNumber")):
            ln.set("number", str(start_no + offset))
        for ct in mem.iter(_q("CommentText")):
            ct.text = item.get("comment") or item["name"]
        for tn in mem.iter(_q("TypeName")):
            tn.text = item.get("type", "BOOL")
        for sv in mem.iter(_q("SimpleValue")):
            sv.set("value", item.get("init", "FALSE"))
        spec.insert(insert_at + offset, mem)


def write_struct_program(path: str | pathlib.Path, program_name: str, st_code: str,
                         struct_name: str = "StructGen",
                         members: list[dict] | None = None,
                         locals_: list[dict] | None = None,
                         sample: str | pathlib.Path = SAMPLE) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    build_struct_program(program_name, st_code, struct_name=struct_name,
                         members=members, locals_=locals_,
                         sample=sample).write(
        p, encoding="utf-8", xml_declaration=True)
    return p


def build_fb_instance(program_name: str, st_code: str,
                      fb_name: str = "FBInst",
                      inst_name: str = "InstFB",
                      fb_body: str = "FB_Bool := NOT FB_Bool;",
                      locals_: list[dict] | None = None,
                      fb_locals: list[dict] | None = None,
                      sample: str | pathlib.Path = SAMPLE) -> ET.ElementTree:
    """建"功能块 + 程序里声明它的实例并调用"的 XML。

    程序侧多一个 `<Variable name="InstFB"><Type><TypeName>FBInst</TypeName></Type></Variable>`，
    正文里调用它（`InstFB();`）。
    """
    locals_ = locals_ or DEFAULT_LOCALS
    tree = build_fb_program(program_name, st_code, fb_name=fb_name, fb_body=fb_body,
                            locals_=locals_, fb_locals=fb_locals, sample=sample)
    root = tree.getroot()
    gn = root.find(_q("Types")).find(_q("GlobalNamespace"))
    prog = next(p for p in gn.findall(_q("Program")) if p.get("name") == program_name)
    vars_el = prog.find(_q("Vars"))
    tpl_var = vars_el.find(_q("Variable"))
    inst = copy.deepcopy(tpl_var)
    inst.set("name", inst_name)
    for tn in inst.iter(_q("TypeName")):
        tn.text = fb_name
    _ensure_line_number(inst, len(locals_) + 1)
    vars_el.append(inst)
    ET.indent(tree, space="\t")
    return tree


def write_fb_instance(path: str | pathlib.Path, program_name: str, st_code: str,
                      fb_name: str = "FBInst", inst_name: str = "InstFB",
                      fb_body: str | None = None,
                      locals_: list[dict] | None = None,
                      fb_locals: list[dict] | None = None,
                      sample: str | pathlib.Path = SAMPLE) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {}
    if fb_body is not None:
        kwargs["fb_body"] = fb_body
    build_fb_instance(program_name, st_code, fb_name=fb_name, inst_name=inst_name,
                      locals_=locals_, fb_locals=fb_locals, sample=sample,
                      **kwargs).write(p, encoding="utf-8", xml_declaration=True)
    return p


# 结构体成员的默认软元件分配（照抄样例 global_label1_4：顶层 3 个 + 嵌套 Struct2 的 3 个）
DEFAULT_MEMBER_ASSIGN = [
    ("member1_1", "B0"), ("member1_2", "W0"), ("member1_3", "B10"),
    ("member1_4", None),          # None = 嵌套结构，用嵌套表
]
DEFAULT_NESTED_ASSIGN = [("member2_1", "B100"), ("member2_2", "W100"),
                         ("member2_3", "B120")]


def _add_struct_assign(var, members=None, nested=DEFAULT_NESTED_ASSIGN) -> None:
    """给结构体类型的变量加 `VariableStructDeviceAssignment`（成员级软元件分配）。

    没有这一块，`局部标签(...)定义检查中` 会报 1 个错（探针 64）；
    加上之后同样一段 XML 就是 0 错（探针 66）。

    `members` 给定时按 [{"name","address"}] 分配（自定义结构体用）；
    为 None 时用样例那套（member1_1…member1_4，最后一个是嵌套 Struct2）。
    """
    add = var.find(_q("AddData"))
    if add is None:
        add = ET.Element(_q("AddData"))
        type_el = var.find(_q("Type"))
        var.insert(list(var).index(type_el) if type_el is not None else len(var), add)
    data = ET.Element(_q("Data"), {
        "name": ADD_NS + "VariableStructDeviceAssignment",
        "handleUnknown": "implementation"})
    assign = ET.SubElement(data, _q("VariableStructDeviceAssignment"))
    if members is not None:
        for item in members:
            attrs = {"name": item["name"]}
            if item.get("address"):
                attrs["address"] = item["address"]
            ET.SubElement(assign, _q("Member"), attrs)
    else:
        for name, addr in DEFAULT_MEMBER_ASSIGN:
            if addr is None:
                holder = ET.SubElement(assign, _q("Member"), {"name": name})
                struct_el = ET.SubElement(holder, _q("Struct"))
                for n2, a2 in nested:
                    ET.SubElement(struct_el, _q("Member"), {"name": n2, "address": a2})
            else:
                ET.SubElement(assign, _q("Member"), {"name": name, "address": addr})
    add.insert(0, data)


def build_struct_var_program(program_name: str, struct_name: str = "StructGen",
                             var_name: str = "S1",
                             st_code: str = "LocBool := NOT LocBool;",
                             members: list[dict] | None = None,
                             assign: list[dict] | None = None,
                             sample: str | pathlib.Path = SAMPLE) -> ET.ElementTree:
    """结构体 + 结构体类型的变量（带成员级软元件分配）+ 程序，一份文档导入。

    实测要点：
      * 结构体与程序必须在**同一份文档**里（先导结构体、再导程序，程序仍报转换错）；
      * 变量必须带 `VariableStructDeviceAssignment`，否则 `局部标签定义检查` 报错；
      * `members` 给定时才自定义成员（`UserDefinedTypeSpec` 的 `<AddData>` 必须留在最后）；
      * 正文**不要引用结构体成员**（`S1.member1_1` 会让转换报错）——成员已经绑到
        B0/W0/B10 这些软元件上，按软元件访问。
    """
    tree = build_struct_program(program_name, st_code, struct_name,
                                members=members,
                                locals_=[{"name": var_name, "type": struct_name},
                                         {"name": "LocBool", "type": "BOOL"}],
                                sample=sample)
    root = tree.getroot()
    gn = root.find(_q("Types")).find(_q("GlobalNamespace"))
    prog = next(p for p in gn.findall(_q("Program")) if p.get("name") == program_name)
    var = next(v for v in prog.find(_q("Vars")).findall(_q("Variable"))
               if v.get("name") == var_name)
    if assign is None and members is not None:
        addrs = ["B0", "W0", "B10", "B20", "W20", "B30", "W30", "B40"]
        assign = [{"name": m["name"], "address": addrs[i % len(addrs)]}
                  for i, m in enumerate(members)]
    _add_struct_assign(var, members=assign)

    if members is None:
        # Struct1 的 member1_4 类型是 Struct2：把 Struct2 也导进来，嵌套成员才有定义
        src_gn = ET.parse(str(sample)).getroot().find(_q("Types")).find(_q("GlobalNamespace"))
        nested = next((d for d in src_gn.findall(_q("DataTypeDecl"))
                       if d.get("name") == "Struct2"), None)
        if nested is not None:
            gn.append(copy.deepcopy(nested))
    ET.indent(tree, space="\t")
    return tree


def write_struct_var_program(path: str | pathlib.Path, program_name: str,
                             struct_name: str = "StructGen", var_name: str = "S1",
                             st_code: str = "LocBool := NOT LocBool;",
                             members: list[dict] | None = None,
                             assign: list[dict] | None = None,
                             sample: str | pathlib.Path = SAMPLE) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    build_struct_var_program(program_name, struct_name, var_name, st_code,
                             members=members, assign=assign,
                             sample=sample).write(p, encoding="utf-8",
                                                  xml_declaration=True)
    return p


def build_struct_global_program(program_name: str, st_code: str,
                                struct_name: str = "StructCust",
                                label_name: str = "GS1",
                                members: list[dict] | None = None,
                                assign: list[dict] | None = None,
                                sample: str | pathlib.Path = SAMPLE) -> ET.ElementTree:
    """结构体 + **全局**结构体标签 + 程序（正文按成员名访问），一份文档导入。

    为什么必须用全局标签：实测局部结构体标签（S1 : StructX 在程序 <Vars> 里）
    按成员名访问会 程序(...)转换中 报错；换成 GlobalVars 里的结构体标签后
    GS1.MyBool := NOT GS1.MyBool; **转换 0 错**（探针 75）。
    导入时还会多出一个阶段 结构体(<名字>)的定义检查中，正好可以当判据。
    """
    members = members or DEFAULT_STRUCT_MEMBERS
    tree = build_struct_program(program_name, st_code, struct_name,
                                members=members, locals_=None, sample=sample)
    root = tree.getroot()
    gn = root.find(_q("Types")).find(_q("GlobalNamespace"))

    if assign is None:
        addrs = ["B0", "W0", "B10", "B20", "W20"]
        assign = [{"name": m["name"], "address": addrs[i % len(addrs)]}
                  for i, m in enumerate(members)]

    src_cfg = ET.parse(str(sample)).getroot().find(_q("Instances")).find(_q("Configuration"))
    gv_tpl = copy.deepcopy(src_cfg.findall(_q("GlobalVars"))[0])
    var_tpl = src_cfg.findall(_q("GlobalVars"))[0].find(_q("Variable"))
    for v in gv_tpl.findall(_q("Variable")):
        gv_tpl.remove(v)
    gvar = copy.deepcopy(var_tpl)
    gvar.set("name", label_name)
    for tn in gvar.iter(_q("TypeName")):
        tn.text = struct_name
    addr = gvar.find(_q("Address"))
    if addr is not None:
        gvar.remove(addr)
    add = gvar.find(_q("AddData"))
    if add is None:
        add = ET.SubElement(gvar, _q("AddData"))
    for d in list(add):
        if "VariableStructDeviceAssignment" in (d.get("name") or ""):
            add.remove(d)
    _add_struct_assign(gvar, members=assign)
    gv_tpl.append(gvar)

    cfg = root.find(_q("Instances")).find(_q("Configuration"))
    cfg.append(gv_tpl)
    ET.indent(tree, space="\t")
    return tree


def write_struct_global_program(path: str | pathlib.Path, program_name: str, st_code: str,
                                struct_name: str = "StructCust",
                                label_name: str = "GS1",
                                members: list[dict] | None = None,
                                assign: list[dict] | None = None,
                                sample: str | pathlib.Path = SAMPLE) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    build_struct_global_program(program_name, st_code, struct_name, label_name,
                                members=members, assign=assign,
                                sample=sample).write(p, encoding="utf-8",
                                                     xml_declaration=True)
    return p
