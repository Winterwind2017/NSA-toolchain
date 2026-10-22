"""能力表：每条 = 一个动作 + 一组从软件读回的判据。

新增能力请用 tools/add_cap.py（会做 cap id 唯一性检查）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

FAMILY_LICENSE = {
    "project": "GX Works3",
    "program": "GX Works3",
    "build": "GX Works3",
    "inspect": "GX Works3",
    "label": "GX Works3",
}


@dataclass(frozen=True)
class Cap:
    id: str
    family: str
    title: str
    action: str
    level: str
    params: dict = field(default_factory=dict)
    expect: dict = field(default_factory=dict)
    reopen: bool = False

    @property
    def license(self) -> str:
        return FAMILY_LICENSE.get(self.family, "unknown")


CAPS: tuple[Cap, ...] = (
    Cap("project.new", "project", "新建 FX5U + ST 工程", "project_new", "L1",
        params={}, expect={"has_window": True, "is_st": True}, reopen=False),
    Cap("project.save", "project", "另存为 .gx3（含读回校验）", "project_save", "L1–L2",
        params={}, expect={"exists": True,
                           "bytes": {"min": 300000.0, "max": 5000000.0},
                           "unit": "FX5U"}, reopen=False),
    Cap("project.meta", "inspect", "解包 .gx3：Config.xml + 条目数", "project_meta", "L1–L2",
        params={}, expect={"unit": "FX5U",
                           "zip_entries": {"min": 50.0, "max": 500.0},
                           "has_config": True}, reopen=False),
    Cap("program.paste_st", "program", "把 ST 代码粘进编辑器并转换", "program_paste_st", "L1–L3",
        params={}, expect={"steps": {"min": 2.0, "max": 200.0}}, reopen=False),
    Cap("program.read_st", "program", "从 .gx3 读回 ST 源码（逐字比对）", "program_read_st",
        "L1–L2", params={}, expect={"matches": True,
                                     "readback_chars": {"min": 10.0, "max": 20000.0},
                                     "lines": {"min": 2.0, "max": 500.0}}, reopen=False),
    Cap("inspect.source_map", "inspect", "步→源码坐标（Row/Col/StrLen）", "inspect_source_map",
        "L2", params={}, expect={"steps": {"min": 2.0, "max": 500.0},
                                  "rows": {"min": 2.0, "max": 500.0},
                                  "snippets": {"min": 2.0, "max": 500.0}}, reopen=False),
    Cap("inspect.devices", "inspect", "读 FX5U 系统软元件模板", "inspect_devices", "L1–L2",
        params={}, expect={"device_rows": {"min": 2900.0, "max": 3000.0},
                            "device_types": {"min": 2.0, "max": 20.0},
                            "commented": {"min": 100.0, "max": 5000.0}}, reopen=False),
    Cap("inspect.mil", "inspect", "读编译后的 IL 文本", "inspect_mil", "L2",
        params={}, expect={"mil_rows": {"min": 1.0, "max": 20.0},
                            "op_count": {"min": 3.0, "max": 1000.0},
                            "mil_chars": {"min": 50.0, "max": 100000.0}}, reopen=False),
    Cap("label.import_xml", "label", "导入全局标签 XML 并读回", "label_import_xml",
        "L2–L3", params={}, expect={"imported": True, "labels_found": 3,
                                    "errors": 0,
                                    "labels_after": {"min": 60.0, "max": 200.0}},
        reopen=False),
    Cap("build.convert_all", "build", "全部转换：从 Progress.txt 读错误数", "build_convert_all",
        "L1–L3", params={}, expect={"errors": 0, "warnings": 0,
                                     "stages": {"min": 3.0, "max": 100.0}}, reopen=False),
    Cap("build.program_check", "build", "程序检查：读「无错误」判定文本", "build_program_check",
        "L2–L3", params={}, expect={"opened": True, "clean": True, "check_errors": 0},
        reopen=False),
    Cap("build.error_detail", "build", "故意写错：定位错在哪个编译阶段", "build_error_detail",
        "L2–L3", params={}, expect={"errors": {"min": 1.0, "max": 999.0},
                                     "failed_stage_count": {"min": 1.0, "max": 6.0}},
        reopen=False),
    Cap("build.locate_error_line", "build", "二分法定位坏行（前缀问编译器）",
        "build_locate_error_line", "L3", params={"bad_line": 5, "total_lines": 8},
        expect={"found_line": 5, "iterations": {"min": 1.0, "max": 6.0}},
        reopen=False),
    Cap("batch.projects", "build", "同会话批量出 3 个工程（各自 0 错）", "batch_projects",
        "L3", params={"batch_count": 3},
        expect={"items": 3, "clean_items": 3,
                "distinct_sources": 3, "content_match": 3}, reopen=False),
    Cap("project.reopen", "project", "存盘→重开→步数仍在（L4）", "project_reopen", "L4",
        params={}, expect={"reopened": True, "steps": {"min": 2.0, "max": 200.0}},
        reopen=True),
)
