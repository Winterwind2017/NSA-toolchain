#!/usr/bin/env python3
"""install_hooks.py —— 装 `pre-push` 钩子（每台机器跑一次）。

钩子做的事（模板：`tools/hooks/pre-push`）：

1. 远端不是 SSH → 拒推（HTTPS 远端会卡在凭据弹窗上）；
2. `ssh -T git@github.com` 不通 → 拒推；
3. `tools/check_consistency.py` 不过 → 拒推（STATUS / registry / VERIFY / 自检 / 测试 五处数字漂移）；
4. `python -m gxkit selftest` 或 `pytest tests` 不过 → 拒推。

只写 `.git/hooks/pre-push`，不碰全局 git 配置；旧钩子自动备份成 `.bak`。
临时绕过：`git push --no-verify`。
"""

from __future__ import annotations

import os
import shutil
import stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, ".git", "hooks", "pre-push")
SRC = os.path.join(ROOT, "tools", "hooks", "pre-push")


def main() -> int:
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        print("不是 git 仓库（找不到 .git/）")
        return 1
    if not os.path.isfile(SRC):
        print("缺少模板：%s" % SRC)
        return 1
    os.makedirs(os.path.dirname(HOOK), exist_ok=True)
    if os.path.exists(HOOK):
        shutil.copy2(HOOK, HOOK + ".bak")
        print("已备份旧钩子 → %s.bak" % HOOK)
    shutil.copy2(SRC, HOOK)
    mode = os.stat(HOOK).st_mode
    os.chmod(HOOK, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("已安装 pre-push 钩子：%s" % HOOK)
    print("现在 `git push` 前会检查：远端协议 / SSH / 五处数字一致 / selftest / 离线测试")
    return 0


if __name__ == "__main__":
    sys.exit(main())
