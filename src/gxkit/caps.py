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
    Cap("build.convert_all", "build", "全部转换：从 Progress.txt 读错误数", "build_convert_all",
        "L1–L3", params={}, expect={"errors": 0, "warnings": 0,
                                     "stages": {"min": 3.0, "max": 100.0}}, reopen=False),
    Cap("project.reopen", "project", "存盘→重开→步数仍在（L4）", "project_reopen", "L4",
        params={}, expect={"reopened": True, "steps": {"min": 2.0, "max": 200.0}},
        reopen=True),
)
