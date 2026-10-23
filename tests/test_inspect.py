"""离线测试：inspect 读取器 + 标签 XML 生成（都不需要 GX Works3）。"""

from __future__ import annotations

import pathlib
import sqlite3
import zipfile

import pytest

from gxkit import inspect as I
from gxkit import xmlgen


def _make_db(path: pathlib.Path, ddl: list[str], rows: list[tuple]) -> None:
    con = sqlite3.connect(str(path))
    for stmt in ddl:
        con.execute(stmt)
    for stmt, params in rows:
        con.execute(stmt, params)
    con.commit()
    con.close()


def _fake_gx3(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "parts"
    d.mkdir()
    _make_db(d / "1_STDB.db",
             ["create table StBlocks(id text, pos real, data text)"],
             [("insert into StBlocks values(?,?,?)", ("blk1", 1.0, "B0 := NOT B0;\r\nW0 := W0 + 1;"))])
    _make_db(d / "1_StepInfo.db",
             ["create table T_Block(Pos real, BlockID text, StepSize int, BodyID int)",
              "create table T_Step(Pos real, ElementIDMacroFB int, BlockID text, MilID int, StepSize int)",
              "create table T_SourcePos(BlockID text, MilID int, SourcePosition text)"],
             [("insert into T_Step values(?,?,?,?,?)", (1.0, 0, "blk1", 0, 3)),
              ("insert into T_Step values(?,?,?,?,?)", (1.0, 0, "blk1", 1, 5)),
              ("insert into T_SourcePos values(?,?,?)", ("blk1", 0, "Row=1,Col=1,StrLen=12")),
              ("insert into T_SourcePos values(?,?,?)", ("blk1", 1, "Row=2,Col=1,StrLen=12"))])
    _make_db(d / "1_MilDB.db",
             ["create table MIL(id text, pos real, data text, ConvTarget int)"],
             [("insert into MIL values(?,?,?,?)",
               ("blk1", 1.0, "V1:10:op=StNotOp:op=StAddOp:END", 0))])
    _make_db(d / "1_DC.db",
             ["create table DEVICE_DATA(SEQ int, DevCode int, ExtCode int, ExtNo int, IsLocal int,"
              " DevNoHigh int, DevNoLow int, BitNo int)",
              "create table COMMENT_DATA(SEQ int, DeviceSEQ int, CmtNo int, CmtData text, DelFlag int)"],
             [("insert into DEVICE_DATA values(?,?,?,?,?,?,?,?)", (1, 2, 0, 0, 0, 0, 0, 0)),
              ("insert into COMMENT_DATA values(?,?,?,?,?)", (1, 1, 7, "异常检测", None))])
    _make_db(d / "LabelData.db",
             ["create table LabelTbl(LabelID text, LabelTypeID int)",
              "create table RowTbl(LabelID text, RowID int, RowNo int, VarType int, BitCount text,"
              " StateFlag int, CheckerState int)",
              "create table ColumnDataTbl(LabelID text, RowID int, ColumnID int,"
              " ColumnStrValue text, ColumnIntValue int)"],
             [("insert into LabelTbl values(?,?)", ("L1", 5123)),
              ("insert into RowTbl values(?,?,?,?,?,?,?)", ("L1", 1, 1, 1, "0", 0, 0)),
              ("insert into ColumnDataTbl values(?,?,?,?,?)", ("L1", 1, 1, "VAR", 4)),
              ("insert into ColumnDataTbl values(?,?,?,?,?)", ("L1", 1, 2, "LBL_A", 0))])

    gx3 = tmp_path / "fake.gx3"
    with zipfile.ZipFile(gx3, "w") as z:
        for f in d.iterdir():
            z.write(f, f.name)
        z.writestr("!!Config.xml",
                   '<Project><Config Unit="FX5U" UnitId="528"/></Project>')
        z.writestr("ConvertData/Progress.txt",
                   "程序(ProgPou)转换中...\nError:0,Warning:0\n"
                   "========== 错误：0、警告：0 ==========\n")
    return gx3


def test_read_st_and_steps(tmp_path: pathlib.Path) -> None:
    g = _fake_gx3(tmp_path)
    assert I.st_source(g).startswith("B0 := NOT B0;")
    steps = I.steps_with_source(g)
    assert len(steps) == 2
    assert steps[0]["row"] == 1 and steps[0]["snippet"].startswith("B0 :=")
    assert steps[1]["row"] == 2


def test_read_mil_devices_labels(tmp_path: pathlib.Path) -> None:
    g = _fake_gx3(tmp_path)
    mil = I.read_mil(g)
    assert mil and "op=StNotOp" in mil[0]["data"]

    dev = I.read_devices(g)
    assert dev["rows"] == 1 and dev["commented"] == 1
    assert dev["sample"][0]["comment"] == "异常检测"

    labels = I.read_labels(g)
    assert any(r["value"] == "LBL_A" for r in labels)


def test_config_and_progress(tmp_path: pathlib.Path) -> None:
    g = _fake_gx3(tmp_path)
    assert I.read_config(g)["Unit"] == "FX5U"
    prog = I.read_progress(g)
    assert prog["errors"] == 0 and prog["stages"][0]["stage"] == "程序(ProgPou)转换中"


def test_cache_invalidated_on_change(tmp_path: pathlib.Path) -> None:
    """工程被重存后必须重新解包（曾因缓存读到导入前的旧标签）。"""
    g = _fake_gx3(tmp_path)
    assert any(r["value"] == "LBL_A" for r in I.read_labels(g))

    # 复制一份并追加一条标签：路径不同 + 内容不同 → 必须读到 LBL_B
    g2 = tmp_path / "fake2.gx3"
    with zipfile.ZipFile(g) as src, zipfile.ZipFile(g2, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, src.read(n))
    d = tmp_path / "more"
    d.mkdir()
    with zipfile.ZipFile(g2) as src:
        for n in src.namelist():
            target = d / n
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(src.read(n))
    con = sqlite3.connect(str(d / "LabelData.db"))
    con.execute("insert into RowTbl values(?,?,?,?,?,?,?)", ("L1", 2, 2, 1, "0", 0, 0))
    con.execute("insert into ColumnDataTbl values(?,?,?,?,?)", ("L1", 2, 2, "LBL_B", 0))
    con.commit()
    con.close()
    g3 = tmp_path / "fake3.gx3"
    with zipfile.ZipFile(g3, "w") as z:
        for f in d.rglob("*"):
            if f.is_file():
                z.write(f, str(f.relative_to(d)).replace("\\", "/"))
    assert any(r["value"] == "LBL_B" for r in I.read_labels(g3))


def test_xmlgen_shape() -> None:
    tree = xmlgen.build()
    root = tree.getroot()
    ns = "%s" % xmlgen.NS
    inst = root.find("{%s}Instances" % ns).find("{%s}Configuration" % ns)
    gv = inst.find("{%s}GlobalVars" % ns)
    assert gv is not None, "GlobalVars 必须在 Instances/Configuration 下"
    names = [v.get("name") for v in gv.findall("{%s}Variable" % ns)]
    assert names == ["LBL_A", "LBL_B", "LBL_C"]
    # 行号必须唯一，否则只会导入第一条
    numbers = [e.get("number") for e in gv.iter("{%s}VariableLineNumber" % ns)]
    assert len(numbers) == len(set(numbers)) == 3


def test_build_program_shape() -> None:
    tree = xmlgen.build_program('PrgGen', 'B0 := NOT B0;')
    ns = xmlgen.NS
    root = tree.getroot()
    gn = root.find('{%s}Types' % ns).find('{%s}GlobalNamespace' % ns)
    progs = gn.findall('{%s}Program' % ns)
    assert [p.get('name') for p in progs] == ['PrgGen']
    assert not progs[0].findall('{%s}Vars' % ns), '必须删掉 Vars，否则引用不存在的类型'
    assert not gn.findall('{%s}FunctionBlock' % ns)
    assert not gn.findall('{%s}DataTypeDecl' % ns)

    cfg = root.find('{%s}Instances' % ns).find('{%s}Configuration' % ns)
    res = cfg.find('{%s}Resource' % ns)
    inst = res.find('{%s}ProgramInstance' % ns)
    assert inst.get('name') == 'PrgGen'
    assert inst.get('typeName') == 'pou'


def test_flat_and_source_matches() -> None:
    assert I.flat('B0 := NOT B0;\r\n\r\nW0 := W0 + 1;') == 'B0:=NOTB0;W0:=W0+1;'


def test_build_fb_program_shape() -> None:
    """顺序（Program 在 FunctionBlock 之前）、无 Parameters、单 Vars、唯一行号。"""
    tree = xmlgen.build_fb_program(
        'PrgFB', 'LocBool := NOT LocBool;', 'FBGen', 'FB_Bool := NOT FB_Bool;')
    ns = xmlgen.NS
    gn = tree.getroot().find('{%s}Types' % ns).find('{%s}GlobalNamespace' % ns)
    tags = [c.tag.replace('{%s}' % ns, '') for c in list(gn)]
    assert tags.index('Program') < tags.index('FunctionBlock'), 'Program 必须在 FunctionBlock 之前'
    assert 'Parameters' not in tags
    assert tags.count('Program') == 1 and tags.count('FunctionBlock') == 1

    fb = gn.find('{%s}FunctionBlock' % ns)
    assert fb.get('name') == 'FBGen'
    assert fb.findall('{%s}Parameters' % ns) == [], 'FunctionBlock 不能带 Parameters'
    assert len(fb.findall('{%s}Vars' % ns)) == 1
    assert [v.get('name') for v in fb.find('{%s}Vars' % ns)] == ['FB_Bool', 'FB_Word']

    prog = gn.find('{%s}Program' % ns)
    assert [v.get('name') for v in prog.find('{%s}Vars' % ns)] == ['LocBool', 'LocWord']
    # 行号在各自 Vars 内唯一（功能块样例变量原本没有行号，由 _ensure_line_number 补上）
    for holder in (fb, prog):
        nums = [e.get('number') for e in holder.iter('{%s}VariableLineNumber' % ns)]
        assert len(nums) == len(set(nums)) == 2, (holder.tag, nums)


def test_build_struct_program_shape() -> None:
    """结构体在程序之后；members=None 时保留样例成员（改成员会让整份导入被丢弃）。"""
    tree = xmlgen.build_struct_program('PrgStruct', 'LocBool := NOT LocBool;', 'StructGen',
                                       members=None, locals_=[{'name': 'LocBool', 'type': 'BOOL'}])
    ns = xmlgen.NS
    gn = tree.getroot().find('{%s}Types' % ns).find('{%s}GlobalNamespace' % ns)
    tags = [c.tag.replace('{%s}' % ns, '') for c in list(gn)]
    assert tags.index('Program') < tags.index('DataTypeDecl')
    dt = gn.find('{%s}DataTypeDecl' % ns)
    assert dt.get('name') == 'StructGen'
    members = dt.find('{%s}UserDefinedTypeSpec' % ns).findall('{%s}Member' % ns)
    assert len(members) == 4, 'members=None 应保留样例的 4 个成员'


def test_build_fb_instance_shape() -> None:
    tree = xmlgen.build_fb_instance('PrgFB', 'InstFB();', 'FBInst', 'InstFB',
                                    fb_body='FB_Bool := NOT FB_Bool;')
    ns = xmlgen.NS
    gn = tree.getroot().find('{%s}Types' % ns).find('{%s}GlobalNamespace' % ns)
    prog = gn.find('{%s}Program' % ns)
    types = {}
    for var in prog.find('{%s}Vars' % ns).findall('{%s}Variable' % ns):
        tn = var.find('{%s}Type' % ns).find('{%s}TypeName' % ns)
        types[var.get('name')] = tn.text
    assert types.get('InstFB') == 'FBInst'
    # 实例变量也要有唯一行号
    nums = [e.get('number') for e in prog.iter('{%s}VariableLineNumber' % ns)]
    assert len(nums) == len(set(nums))


def test_build_struct_var_program_shape() -> None:
    """结构体变量必须带成员级软元件分配；嵌套 Struct2 也要一起导入。"""
    tree = xmlgen.build_struct_var_program('PrgSV', 'StructGen', 'S1')
    ns = xmlgen.NS
    gn = tree.getroot().find('{%s}Types' % ns).find('{%s}GlobalNamespace' % ns)
    tags = [c.tag.replace('{%s}' % ns, '') for c in list(gn)]
    assert tags.count('DataTypeDecl') == 2, 'StructGen + Struct2'
    prog = gn.find('{%s}Program' % ns)
    var = next(v for v in prog.find('{%s}Vars' % ns).findall('{%s}Variable' % ns)
               if v.get('name') == 'S1')
    datas = [d.get('name', '') for d in var.find('{%s}AddData' % ns)]
    assert any('VariableStructDeviceAssignment' in d for d in datas), '必须有成员级软元件分配'
    assign = var.find('{%s}AddData' % ns).find(
        '{%s}Data' % ns + "[@name='http://www.mitsubishielectric.com/xml/VariableStructDeviceAssignment']")
    members = assign.find('{%s}VariableStructDeviceAssignment' % ns).findall('{%s}Member' % ns)
    assert [m.get('name') for m in members] == ['member1_1', 'member1_2', 'member1_3', 'member1_4']
    assert members[-1].find('{%s}Struct' % ns) is not None, '嵌套成员要套 Struct'
