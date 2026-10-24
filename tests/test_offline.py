"""离线测试：不需要 GX Works3，只测判据、日志解析、能力表自洽。"""

from __future__ import annotations

import json
import pathlib
import zipfile

import pytest

from gxkit import caps
from gxkit.judges import check, judge, tol


def test_tolerance_by_magnitude() -> None:
    assert tol(500) == 0.5
    assert tol(1.5) == 1e-3
    assert tol(0.01) == 1e-6


def test_check_scalars_and_ranges() -> None:
    assert check("n", 3, 3) is None
    assert check("n", 3, 4) is not None
    assert check("n", 120, {"min": 100.0, "max": 200.0}) is None
    assert check("n", 99, {"min": 100.0, "max": 200.0}) is not None
    assert check("s", "FX5U", "FX5U") is None
    assert check("s", None, "FX5U") is not None
    assert check("b", True, True) is None


def test_judge_collects_all_failures() -> None:
    fails = judge({"a": 1, "b": "x"}, {"a": 2, "b": "x"})
    assert len(fails) == 1 and "a" in fails[0]


def test_caps_unique_and_well_formed() -> None:
    ids = [c.id for c in caps.CAPS]
    assert len(ids) == len(set(ids))
    for c in caps.CAPS:
        assert c.expect, c.id
        assert c.license == "GX Works3"


def test_actions_registered() -> None:
    from gxkit.actions import ACTIONS

    for c in caps.CAPS:
        assert c.action in ACTIONS, c.action


def test_read_config_and_progress(tmp_path: pathlib.Path) -> None:
    from gxkit.session import read_config, read_progress

    gx3 = tmp_path / "fake.gx3"
    with zipfile.ZipFile(gx3, "w") as z:
        z.writestr("!!Config.xml",
                   '<?xml version="1.0" encoding="utf-8"?>\n'
                   '<Project><Config Unit="FX5U" UnitId="528" Title="" /></Project>')
        z.writestr("ConvertData/Progress.txt",
                   "------ 全部转换(重新分配)开始 ------\n"
                   "程序文件管理列表创建中...\n"
                   "程序(ProgPou)检查中...\nError:0,Warning:0\n"
                   "========== 全部转换(重新分配)结束  错误：0、警告：0 ==========\n")
    cfg = read_config(gx3)
    assert cfg["Unit"] == "FX5U" and cfg["UnitId"] == "528"
    prog = read_progress(gx3)
    assert prog["found"] and prog["errors"] == 0 and prog["warnings"] == 0
    assert prog["stages"] and prog["stages"][0]["errors"] == 0


def test_cli_selftest_and_caps(capsys: pytest.CaptureFixture[str]) -> None:
    from gxkit.cli import main

    assert main(["selftest"]) == 0
    assert "自检通过" in capsys.readouterr().out
    assert main(["caps"]) == 0
    assert "共 %d 条" % len(caps.CAPS) in capsys.readouterr().out


def test_local_vars_have_no_remark() -> None:
    """局部变量不能带 VariableRemark（会让转换报 2 错、局部标签不落地）。"""
    from gxkit import xmlgen

    tree = xmlgen.build_fb_instance("PrgX", "LocBool := NOT LocBool;",
                                    fb_name="FBInst", inst_name="InstFB")
    ns = xmlgen.NS
    for tag in ("Program", "FunctionBlock"):
        for pou in tree.getroot().iter("{%s}%s" % (ns, tag)):
            for vs in pou.findall("{%s}Vars" % ns):
                for var in vs.findall("{%s}Variable" % ns):
                    add = var.find("{%s}AddData" % ns)
                    if add is None:
                        continue
                    names = [d.get("name") or "" for d in list(add)]
                    assert not any("VariableRemark" in n for n in names), var.get("name")
