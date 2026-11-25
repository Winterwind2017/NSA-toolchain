"""打印本机默认焊件轮廓和它的配置名。不改模型。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from swkit.core.com import dispatch  # noqa: E402
from swkit.verified.weldment import profile_configurations  # noqa: E402
from swkit.weldment_library import default_profile, list_profiles  # noqa: E402


def main() -> int:
    found = default_profile()
    print("roots_ok", bool(list_profiles()))
    print("default", found)
    if not found:
        return 2
    app = dispatch("SldWorks.Application")
    if os.environ.get("NSA_CLOSE_TEST_DOCS") == "1":
        app.CloseAllDocuments(True)
    names = profile_configurations(app, found["path"])
    print("configs", names)
    return 0 if names else 1


if __name__ == "__main__":
    raise SystemExit(main())
