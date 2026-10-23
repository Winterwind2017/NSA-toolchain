"""改造 xmlgen：模板走"缓存骨架 + 指纹"，并保留手写骨架做对照。"""

import pathlib

P = pathlib.Path(r"D:\bililive\gxkit\src\gxkit\xmlgen.py")
t = P.read_text(encoding="utf-8")

t = t.replace("from __future__ import annotations\n\nimport copy\nimport pathlib",
              "from __future__ import annotations\n\nimport copy\nimport json\nimport os\nimport pathlib", 1)

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
assert "def _q(tag: str) -> str:" in t
t = t.replace("def _q(tag: str) -> str:", HELPERS, 1)

t = t.replace("sample: str | pathlib.Path = TEMPLATE", "sample: str | pathlib.Path | None = None")

FUNCS = ["def build(", "def write(", "def build_program(", "def write_program(",
         "def build_fb_program(", "def write_fb_program(", "def build_struct_program(",
         "def write_struct_program(", "def build_fb_instance(", "def write_fb_instance(",
         "def build_struct_var_program(", "def write_struct_var_program(",
         "def build_struct_global_program(", "def write_struct_global_program("]

INJECT = "    sample = sample or template_path()\n"
for fn in FUNCS:
    i = t.find(fn)
    if i < 0:
        print("missing:", fn)
        continue
    j = t.find('"""', i)
    insert_at = None
    if j >= 0:
        k = t.find('"""', j + 3)
        if k >= 0 and "\n" in t[j:k]:
            insert_at = t.find("\n", k) + 1
    if insert_at is None:
        insert_at = t.find("\n", i) + 1
    if "sample = sample or template_path()" in t[i:i + 2500]:
        continue
    t = t[:insert_at] + INJECT + t[insert_at:]

P.write_text(t, encoding="utf-8")
print("patched; template_path() call sites:", t.count("template_path()"))
