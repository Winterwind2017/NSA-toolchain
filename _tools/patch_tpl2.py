"""把 xmlgen 改成"缓存骨架 + 指纹"策略（干净版）。

只改四处：
  1. 头部注释 + MANUAL_TEMPLATE 常量
  2. 依赖加 json/os
  3. 插入 template_path()/use_manual_template()/缓存逻辑
  4. 所有 ET.parse(str(sample)) → ET.parse(str(sample or template_path()))
"""

import pathlib

P = pathlib.Path(r"D:\bililive\gxkit\src\gxkit\xmlgen.py")
t = P.read_text(encoding="utf-8")

t = t.replace("from __future__ import annotations\n\nimport copy\nimport pathlib",
              "from __future__ import annotations\n\nimport copy\nimport json\nimport os\nimport pathlib", 1)

COMMENT_OLD = '''SAMPLE = pathlib.Path(
    r"D:\\Program Files (x86)\\MELSOFT\\GPPW3\\SampleData\\IEC61131-10XML\\Sample.xml")'''
COMMENT_NEW = '''# 模板来源（按优先级）：
#   1. 环境变量 GXKIT_TEMPLATE 指向的文件
#   2. 缓存骨架 %LOCALAPPDATA%/gxkit/skeleton.xml（首次从下面的 Sample.xml 复制并记指纹；
#      MELSOFT 升级导致指纹变化时自动重建）
#   3. MELSOFT 安装目录里的 Sample.xml
#
# 为什么没有完全自给自足：手写过一份等价骨架（templates/base.xml），程序/标签/全局
# 结构体都能导入，但**局部标签**（结构体变量、功能块实例所必需）不会被导入
# （locals_found=0、程序(...)转换中 报 2 错）。改 PouProperties title、调整 AddData
# 顺序、去掉 VariableRemark/InitialValue 都试过仍未解开，属未打通的逆向项。
MANUAL_TEMPLATE = pathlib.Path(__file__).with_name("templates") / "base.xml"

SAMPLE = pathlib.Path(
    r"D:\\Program Files (x86)\\MELSOFT\\GPPW3\\SampleData\\IEC61131-10XML\\Sample.xml")'''
assert COMMENT_OLD in t
t = t.replace(COMMENT_OLD, COMMENT_NEW, 1)

HELPERS = '''_SKELETON_CACHE: pathlib.Path | None = None


def _cache_dir() -> pathlib.Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    d = pathlib.Path(base) / "gxkit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fingerprint(path: pathlib.Path) -> dict:
    import hashlib
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def template_path() -> pathlib.Path:
    """返回可用骨架；缓存与安装样例的指纹不一致时自动重建。"""
    global _SKELETON_CACHE
    if _SKELETON_CACHE is not None:
        return _SKELETON_CACHE

    env = os.environ.get("GXKIT_TEMPLATE")
    if env:
        p = pathlib.Path(env)
        if not p.exists():
            raise RuntimeError("GXKIT_TEMPLATE 指向的文件不存在：%s" % p)
        _SKELETON_CACHE = p
        return p

    cache = _cache_dir() / "skeleton.xml"
    meta = _cache_dir() / "skeleton.json"
    if not SAMPLE.exists():
        if cache.exists():
            _SKELETON_CACHE = cache
            return cache
        raise RuntimeError(
            "找不到 MELSOFT 样例，也没有缓存骨架：%s\\n"
            "解决办法：设 GXKIT_TEMPLATE=<可用的 IEC61131-10 XML>，或确认 GX Works3 已安装" % SAMPLE)

    want = _fingerprint(SAMPLE)
    have = {}
    if meta.exists() and cache.exists():
        try:
            have = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            have = {}
    if have.get("sha256") != want["sha256"] or not cache.exists():
        cache.write_bytes(SAMPLE.read_bytes())
        meta.write_text(json.dumps({"source": str(SAMPLE), **want}, ensure_ascii=False),
                        encoding="utf-8")
    _SKELETON_CACHE = cache
    return cache


def use_manual_template() -> pathlib.Path:
    """切到我们自己手写的骨架（局部标签导入不了，仅用于对照/测试）。"""
    global _SKELETON_CACHE
    _SKELETON_CACHE = MANUAL_TEMPLATE
    return MANUAL_TEMPLATE


def _q(tag: str) -> str:'''
t = t.replace("def _q(tag: str) -> str:", HELPERS, 1)

t = t.replace("sample: str | pathlib.Path = SAMPLE", "sample: str | pathlib.Path | None = None")
n = t.count("ET.parse(str(sample))")
t = t.replace("ET.parse(str(sample))", "ET.parse(str(sample or template_path()))")
print("ET.parse sites replaced:", n)

P.write_text(t, encoding="utf-8")
print("done")
