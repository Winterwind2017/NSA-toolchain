"""scripts/draft_fixture_verify.py —— 用真实分型线夹具验收拔模分析

用法：
    python scripts/draft_fixture_verify.py "D:\\bililive\\acad_out\\p2\\draft_fixture.SLDPRT"

做的事：
1. 把夹具**复制**到临时目录再打开（绝不改你的原文件）
2. 找分型线特征 → `GetDefinition()` → QI `IPartingLineFeatureData`
3. `DraftAnalysis(1°)` + `GetFacesByTypeCount(0..3)`
4. 打印结果；通过时给出可直接粘进 registry.py 的证据行

退出码：0 通过 / 4 未通过 / 2 文件或环境问题
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = os.path.abspath(sys.argv[1])
    if not os.path.isfile(src):
        print("找不到文件：%s" % src)
        return 2

    from swkit.core.com import pyw
    from swkit.verified import draft as D

    tmpdir = tempfile.mkdtemp(prefix="swkit_draft_")
    dst = os.path.join(tmpdir, os.path.basename(src))
    shutil.copy2(src, dst)
    print("夹具副本：%s" % dst)

    app = pyw().Dispatch("SldWorks.Application")
    app.CloseAllDocuments(True)
    if app.OpenDoc(dst, 1) is None:
        print("打开失败：%s" % dst)
        return 2
    doc = pyw().Dispatch(app.ActiveDoc)

    feat = D.find_parting_line(doc)
    print("分型线特征：%s" % (None if feat is None else
                            "%s / %s" % (D.val(feat, "GetTypeName2"), D.val(feat, "Name"))))

    res = D.analyze(doc, 1.0)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))

    if not res.get("ok"):
        print("\n未通过：%s" % ((res.get("detail") or {}).get("error") or "判据不成立"))
        return 4

    counts = (res.get("detail") or {}).get("faces_by_type") or {}
    print("\n通过。可粘进 registry.py 的证据：")
    print('    _e("sw_analyze_draft", "feature",')
    print('       "IPartingLineFeatureData.DraftAnalysis + GetFacesByTypeCount",')
    print('       "%s（分型线特征 %s）",' % (
        "、".join("%s %s" % (k, v) for k, v in counts.items()),
        (res.get("detail") or {}).get("feature")))
    print('       "分型线本身无法用 API 创建（CreateDefinition 无该类型、InsertMoldPartingLine 恒 None），读取侧照常可用"),')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
