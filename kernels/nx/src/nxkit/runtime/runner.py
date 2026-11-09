"""run_journal 的入口：读 job → 逐条执行 → 每条立刻落盘 → 打印完成标记。

在 NX 进程内运行；只有 `NXOpen` 可用，所以这里不 import 任何宿主侧重模块。
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback


def _dump(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main() -> int:
    job_path = sys.argv[1]
    with open(job_path, encoding="utf-8") as fh:
        job = json.load(fh)

    sys.path.insert(0, job["src"])
    import NXOpen                                    # noqa: F401
    from nxkit.runtime import actions

    result_path = job["result"]
    result = {"schema": 1, "caps": [], "nx_version": None,
              "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        import NXOpen
        s = NXOpen.Session.GetSession()
        result["license_bundles"] = []
        result["nx_version"] = str(getattr(NXOpen, "Version", ""))
    except Exception:
        pass
    _dump(result_path, result)

    for cap in job["caps"]:
        rec = {"id": cap["id"], "ok": False, "reads": {}, "errors": [],
               "seconds": 0.0}
        t0 = time.time()
        try:
            rec["reads"] = actions.run(cap.get("action") or cap["id"],
                                       cap.get("params") or {},
                                       job["workdir"], rec)
            rec["ok"] = True
        except Exception:
            rec["errors"].append(traceback.format_exc(limit=4))
        rec["seconds"] = round(time.time() - t0, 2)
        result["caps"].append(rec)
        _dump(result_path, result)

    result["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _dump(result_path, result)
    print("NXKIT_DONE " + result_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
