"""lint_scripts 的测试：好文件通过、坏文件被抓住并给中文引号提示。"""

from __future__ import annotations

import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "lint_scripts.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(ROOT))


def test_lint_scripts_passes_repo(tmp_path: pathlib.Path) -> None:
    good = tmp_path / "good.py"
    good.write_text("X = 1\nprint(X)\n", encoding="utf-8")
    r = _run(str(good))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_lint_scripts_catches_bad_quote(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad.py"
    # 中文串里用 ASCII 引号 → SyntaxError；工具应报错并给出「」提示
    bad.write_text('MSG = "检查"这个"词"\n', encoding="utf-8")
    r = _run(str(bad))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "HINT" in r.stdout
    assert "「」" in r.stdout
