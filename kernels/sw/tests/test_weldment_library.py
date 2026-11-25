"""焊件轮廓库只做定位，不把 SolidWorks 自带文件复制进仓库。"""

from __future__ import annotations

import os

import pytest

from swkit.weldment_library import default_profile, list_profiles, profile_roots


def test_profile_roots_follow_programdata():
    roots = profile_roots()
    program_data = os.environ.get("PROGRAMDATA")
    if not program_data:
        assert isinstance(roots, list)
        return
    for root in roots:
        if os.environ.get("NSA_WELDMENT_PROFILES") and root == os.environ["NSA_WELDMENT_PROFILES"]:
            continue
        assert "weldment profiles" in root
        assert root.startswith(program_data)


def test_default_profile_is_a_real_file_when_solidworks_library_is_installed():
    found = default_profile()
    if found is None:
        pytest.skip("这台机器没有焊件轮廓库")
    assert os.path.isfile(found["path"])
    assert found["name"].lower().endswith(".sldlfp")
    assert found in list_profiles()
