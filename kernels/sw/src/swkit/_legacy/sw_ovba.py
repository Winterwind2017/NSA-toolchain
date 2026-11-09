"""MS-OVBA 最小实现 + SolidWorks `.swp` 生成器（纯标准库 + pywin32）。

依据：[MS-OVBA] Office VBA File Format Structure
  - 2.4.1 压缩容器 / 压缩块
  - 2.3.4.2 dir 流（含 PROJECTCODEPAGE / PROJECTMODULES / MODULESTREAMNAME / MODULEOFFSET）
  - 2.3.4.1 _VBA_PROJECT（写时 Version 必须 = 0xFFFF）
  - 2.3.4.3 模块流布局：PerformanceCache(MODULEOFFSET 字节) + CompressedSourceCode

设计要点（避免写 LZ 压缩器）：
  MS-OVBA 的**原始块**（CompressedChunkFlag=0）恰好携带 4096 字节且原样解出。
  所以只要把源码**补齐到 4096 的整数倍**（用无害的尾部空行/注释），
  就能全部用原始块编码 —— 解压结果与源码逐字节相同，无需任何匹配算法。

用法（命令行自测）：
  python sw_ovba.py selftest                 # 解压真实 .swp 的 dir 做验证
  python sw_ovba.py dump <swp>               # 打印结构
  python sw_ovba.py build <swp> <模块名> <源码文件> <输出.swp>
"""

import os
import struct
import sys

# ── MS-OVBA 压缩容器 ────────────────────────────────────────────────────────

CONTAINER_SIG = 0x01
CHUNK_SIG = 0b011           # CompressedChunkSignature（3 位）
MAX_CHUNK = 4096            # 解压后每块上限


def _ceil_log2(d):
    n = 0
    while (1 << n) < d:
        n += 1
    return n


def _copy_token_help(cur, chunk_start):
    """按当前位置决定 copy token 的位分配（编解码必须一致）。"""
    diff = cur - chunk_start
    bit_count = max(4, _ceil_log2(diff))
    length_mask = 0xFFFF >> bit_count
    offset_mask = (~length_mask) & 0xFFFF
    return length_mask, offset_mask, bit_count


def decompress(data):
    """MS-OVBA 解压。"""
    if not data:
        raise ValueError("空数据")
    if data[0] != CONTAINER_SIG:
        raise ValueError(f"压缩容器签名错：0x{data[0]:02X}（应为 0x01）")
    pos = 1
    out = bytearray()
    while pos < len(data):
        if pos + 2 > len(data):
            raise ValueError("块头越界")
        header = data[pos] | (data[pos + 1] << 8)
        size = (header & 0x0FFF) + 3
        sig = (header >> 12) & 0x7
        flag = (header >> 15) & 0x1
        if sig != CHUNK_SIG:
            raise ValueError(f"压缩块签名错：0b{sig:03b}（应为 0b011）")
        chunk_start = pos
        chunk_end = min(len(data), chunk_start + size)
        pos = chunk_start + 2
        dcs = len(out)
        if flag == 0:
            # 原始块：恰好 4096 字节，原样追加
            if pos + MAX_CHUNK > len(data):
                raise ValueError("原始块数据不足 4096 字节")
            out += data[pos:pos + MAX_CHUNK]
            pos += MAX_CHUNK
        else:
            while pos < chunk_end:
                fb = data[pos]
                pos += 1
                for bit in range(8):
                    if pos >= chunk_end:
                        break
                    if not (fb >> bit) & 1:
                        out.append(data[pos])
                        pos += 1
                    else:
                        if pos + 2 > chunk_end:
                            raise ValueError("copy token 越界")
                        tok = data[pos] | (data[pos + 1] << 8)
                        pos += 2
                        lm, om, bc = _copy_token_help(len(out), dcs)
                        length = (tok & lm) + 3
                        offset = ((tok & om) >> (16 - bc)) + 1
                        src = len(out) - offset
                        if src < dcs:
                            raise ValueError("copy token 引用了块外数据")
                        for i in range(length):
                            out.append(out[src + i])
    return bytes(out)


def _literal_chunk(payload):
    """字面量块（token 压缩，全部为 literal）。len(payload) 必须 <= 3640。"""
    enc = bytearray()
    i = 0
    while i < len(payload):
        group = payload[i:i + 8]
        enc.append(0x00)          # 8 个 flag 位全 0 = 8 个字面量
        enc.extend(group)
        i += len(group)
    return bytes(enc)


def compress(data, pad_byte=b"\r\n"):
    """MS-OVBA 压缩（原始块 + 字面量尾块；必要时用无害尾部填充对齐）。

    返回 (compressed_bytes, padded_source)。若发生过填充，padded_source != data。
    """
    src = bytes(data)
    # 让尾块 <= 3640 → 全块走原始块，尾块走字面量块
    rem = len(src) % MAX_CHUNK
    if rem > 3640 or (rem == 0 and len(src) == 0):
        pad = MAX_CHUNK - rem if rem else 0
        if rem == 0:
            pad = 0
        else:
            pad = MAX_CHUNK - rem
        src = src + (pad_byte * ((pad // len(pad_byte)) + 1))[:pad]
    out = bytearray([CONTAINER_SIG])
    pos = 0
    while pos < len(src):
        chunk = src[pos:pos + MAX_CHUNK]
        pos += len(chunk)
        if len(chunk) == MAX_CHUNK:
            header = ((MAX_CHUNK + 2 - 3) & 0x0FFF) | (CHUNK_SIG << 12) | (0 << 15)
            out += struct.pack("<H", header)
            out += chunk
        else:
            enc = _literal_chunk(chunk)
            if len(enc) > MAX_CHUNK:
                raise ValueError("尾块字面量编码超 4096，需要真正实现 LZ 压缩")
            header = ((len(enc) + 2 - 3) & 0x0FFF) | (CHUNK_SIG << 12) | (1 << 15)
            out += struct.pack("<H", header)
            out += enc
    return bytes(out), src


# ── dir 流解析（只取我们需要的最小字段） ────────────────────────────────────

def parse_dir(d):
    """从已解压的 dir 流里取 PROJECTCODEPAGE 与各模块的 (名称, 流名, MODULEOFFSET)。

    实现说明：
      - PROJECTINFORMATION 段严格按记录顺序解析（只关心 PROJECTCODEPAGE）
      - PROJECTREFERENCES 段**不解析**（记录布局复杂且我们不需要）——
        改为在字节流里扫描 `0F 00 02 00 00 00`（PROJECTMODULES + Size=2）定位
      - MODULE 记录严格按规范顺序解析（顺序是固定的）
    """
    def u16(p):
        return struct.unpack_from("<H", d, p)[0]

    def u32(p):
        return struct.unpack_from("<I", d, p)[0]

    # ── 1) PROJECTINFORMATION：找 PROJECTCODEPAGE ──────────────────────────
    codepage = 1252
    pos = 0
    while pos + 6 <= len(d):
        rid = u16(pos)
        size = u32(pos + 2)
        if rid == 0x0003:                       # PROJECTCODEPAGE（Size=2）
            codepage = u16(pos + 6)
            pos += 6 + size
        elif rid in (0x0001, 0x0002, 0x0014, 0x0007, 0x0008, 0x004A):
            pos += 6 + size                     # id + Size + 值
        elif rid == 0x0009:                     # PROJECTVERSION（无 Size）
            pos += 2 + 4 + 4 + 2
        elif rid in (0x0004,):                  # Size + name
            pos += 6 + size
        elif rid in (0x0005, 0x0006, 0x000C):   # Size + s + Reserved(2) + Size2 + s2
            pos += 6 + size + 2
            if pos + 4 > len(d):
                break
            pos += 4 + u32(pos)
        else:
            break

    # ── 2) 扫描 PROJECTMODULES ────────────────────────────────────────────
    pat = b"\x0f\x00\x02\x00\x00\x00"
    idx = d.find(pat, 0)
    if idx < 0:
        return {"codepage": codepage, "modules": [], "error": "未找到 PROJECTMODULES"}
    p = idx + 6
    count = u16(p)
    p += 2
    if p + 8 <= len(d) and u16(p) == 0x0013:    # PROJECTCOOKIE: id + Size(4)=2 + cookie(2)
        p += 6 + u32(p + 2)

    # ── 3) 逐个 MODULE 记录（顺序固定）────────────────────────────────────
    modules = []
    for _ in range(count):
        try:
            if u16(p) != 0x0019:                # MODULENAME
                break
            n = u32(p + 2)
            name = d[p + 6:p + 6 + n]
            p += 6 + n
            if u16(p) == 0x0047:                # MODULENAMEUNICODE（可选）
                p += 6 + u32(p + 2)
            if u16(p) != 0x001A:                # MODULESTREAMNAME
                break
            n = u32(p + 2)
            stream = d[p + 6:p + 6 + n]
            p += 6 + n
            if u16(p) != 0x0032:                # Reserved
                break
            p += 2
            p += 4 + u32(p)                     # SizeUnicode + 内容
            if u16(p) != 0x001C:                # MODULEDOCSTRING
                break
            p += 6 + u32(p + 2)
            if u16(p) != 0x0048:                # Reserved
                break
            p += 2
            p += 4 + u32(p)
            if u16(p) != 0x0031:                # MODULEOFFSET
                break
            offset = u32(p + 6)
            p += 10
            if u16(p) != 0x001E:                # MODULEHELPCONTEXT
                break
            p += 6 + u32(p + 2)
            if u16(p) != 0x002C:                # MODULECOOKIE  id + Size(4)=2 + cookie(2)
                break
            p += 6 + u32(p + 2)
            if u16(p) not in (0x0021, 0x0022):  # MODULETYPE  ★ id + Reserved(4) = 6 字节
                break
            raise_mt = u16(p)
            p += 6
            for opt in (0x0025, 0x0028):        # MODULEREADONLY / MODULEPRIVATE：也是 id + Reserved(4)
                if p + 6 <= len(d) and u16(p) == opt:
                    p += 6
            if p + 6 <= len(d) and u16(p) == 0x002B:   # terminator + Reserved(4)
                p += 6
            else:
                break
            modules.append((name, stream, offset, raise_mt))
        except (struct.error, IndexError):
            break
    return {"codepage": codepage, "modules": modules}


# ── CFB 读写（pywin32 结构化存储） ──────────────────────────────────────────

STGM_READ = 0x00000000
STGM_READWRITE = 0x00000002
STGM_SHARE_EXCLUSIVE = 0x00000010
STGM_CREATE = 0x00001000
RO = STGM_READ | STGM_SHARE_EXCLUSIVE
RW = STGM_READWRITE | STGM_SHARE_EXCLUSIVE

SWP_PATH = ["apc", "The VBA Project", "_VBA_Project"]


def _read_all(stream):
    out = b""
    while True:
        d = stream.Read(1 << 20)
        if not d:
            break
        out += d
    return out


def _open_vba(path, mode):
    """打开 <swp> 的 VBA storage。

    ★ 坑：IStorage 的子对象依赖父对象存活 —— 若中途把父对象的引用丢掉
      （例如 `cur = cur.OpenStorage(...)`），会报
      `试图使用一个已不复存在的对象` (STG_E_REVERTED)。
      所以这里把所有中间对象都存进 keepalive 列表。
    """
    import pythoncom
    keep = []
    stg = pythoncom.StgOpenStorage(path, None, mode, None, 0)
    keep.append(stg)
    cur = stg
    for name in SWP_PATH:
        cur = cur.OpenStorage(name, None, mode, None, 0)
        keep.append(cur)
    vba = cur.OpenStorage("VBA", None, mode, None, 0)
    keep.append(vba)
    return keep, vba


def dump(path):
    import pythoncom
    STGTY = {0: "EMPTY", 1: "STORAGE", 2: "STREAM", 5: "ROOT"}

    def walk(stg, prefix="", depth=0, maxd=5):
        for it in list(stg.EnumElements()):
            name, typ = it[0], it[1]
            if typ == 1 and depth < maxd:
                print("  " * depth + f"[{prefix}{name}/]")
                try:
                    walk(stg.OpenStorage(name, None, RO, None, 0), prefix + name + "/",
                         depth + 1, maxd)
                except Exception as e:  # noqa: BLE001
                    print("  " * (depth + 1) + f"打不开 {type(e).__name__}")
            elif typ == 2:
                try:
                    data = _read_all(stg.OpenStream(name, None, RO, 0))
                    print("  " * depth + f"{prefix}{name}  {len(data)}B  头={data[:10].hex()}")
                except Exception as e:  # noqa: BLE001
                    print("  " * depth + f"{prefix}{name}  读失败 {type(e).__name__}")
    walk(pythoncom.StgOpenStorage(path, None, RO, None, 0))


def selftest(swp=None):
    """用真实 .swp 验证解压器与 dir 解析。"""
    swp = swp or r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\Simulation\enable.swp"
    print(f"=== selftest on {swp} ===")
    _, vba = _open_vba(swp, RO)
    dir_raw = _read_all(vba.OpenStream("dir", None, RO, 0))
    print(f"  dir 压缩后 {len(dir_raw)}B")
    dir_plain = decompress(dir_raw)
    print(f"  dir 解压后 {len(dir_plain)}B")
    info = parse_dir(dir_plain)
    print(f"  PROJECTCODEPAGE = {info['codepage']}")
    if info.get("error"):
        print("  解析错误:", info["error"])
    print("  模块:")
    for name, stream, off, mt in info["modules"]:
        nm = name.decode("mbcs", "replace") if name else None
        st = stream.decode("mbcs", "replace") if stream else None
        print(f"    name={nm!r:<20} stream={st!r:<20} MODULEOFFSET={off} MODULETYPE=0x{mt:04X}")
    # 用第一个模块流验证"前缀 + 压缩源码"的解读
    for name, stream, off, mt in info["modules"]:
        if not stream:
            continue
        raw = _read_all(vba.OpenStream(stream.decode("mbcs", "replace"), None, RO, 0))
        print(f"  {stream!r} 流长 {len(raw)}B，offset={off}，"
              f"压缩部分头={raw[off:off+4].hex()}")
        src = decompress(raw[off:])
        print(f"    解压出 {len(src)}B 源码，前 200 字节：")
        print("    " + src[:200].decode("mbcs", "replace").replace("\r\n", "\n    "))
        # 往返验证压缩器
        comp, padded = compress(src)
        back = decompress(comp)
        print(f"    压缩往返: 原文 {len(src)}B -> 压缩 {len(comp)}B -> 解压 {len(back)}B"
              f"  一致={back == src}")
        break
    # 顺带验证 _VBA_PROJECT
    try:
        vp = _read_all(vba.OpenStream("_VBA_PROJECT", None, RO, 0))
        r1, ver = struct.unpack_from("<HH", vp, 0)
        print(f"  _VBA_PROJECT: Reserved1=0x{r1:04X} Version=0x{ver:04X} 长 {len(vp)}B")
    except Exception as e:  # noqa: BLE001
        print("  _VBA_PROJECT 读取失败:", e)


def build_swp(template_swp, source_text, out_path, module_stream=None,
              codepage=1252):
    """由模板 .swp 生成一个新 .swp：把目标标准模块的源码换成 source_text。

    做法（[MS-OVBA] 2.3.4.3 的"最小源码替换"策略）：
      1) 复制模板（**绝不动原文件**）
      2) 读 VBA/dir -> 找到目标模块的 MODULESTREAMNAME 与 MODULEOFFSET
      3) 新模块流 = 原流前 MODULEOFFSET 字节 + compress(新源码)
         （前缀是性能缓存，保留即可；反正下一步会禁用缓存）
      4) 把 _VBA_PROJECT 的 Version 字段置 0xFFFF（强制忽略陈旧性能缓存）
      5) Commit

    module_stream 留空时自动选**第一个标准模块**（MODULETYPE=0x0021）。
    返回 dict，含实际使用的模块流名、偏移、字节数等，便于核验。
    """
    import gc
    import shutil

    import pythoncom

    if not os.path.isfile(template_swp):
        raise FileNotFoundError(f"模板 .swp 不存在: {template_swp}")
    shutil.copy2(template_swp, out_path)
    gc.collect()

    RWX = STGM_READWRITE | STGM_SHARE_EXCLUSIVE
    keep = []
    stg = pythoncom.StgOpenStorage(out_path, None, RWX, None, 0)
    keep.append(stg)
    cur = stg
    for name in SWP_PATH:
        cur = cur.OpenStorage(name, None, RWX, None, 0)
        keep.append(cur)
    vba = cur.OpenStorage("VBA", None, RWX, None, 0)
    keep.append(vba)

    dir_plain = decompress(_read_all(vba.OpenStream("dir", None, RW, 0)))
    info = parse_dir(dir_plain)
    cp = info["codepage"] or codepage
    target = None
    for name, stream, off, mt in info["modules"]:
        sname = stream.decode("mbcs", "replace") if stream else None
        if module_stream:
            if sname == module_stream or (name and name.decode("mbcs", "replace") == module_stream):
                target = (name, sname, off, mt)
                break
        elif mt == 0x0021:                 # 第一个标准模块
            target = (name, sname, off, mt)
            break
    if target is None:
        raise RuntimeError(f"在模板里找不到模块 {module_stream!r}；"
                           f"可用: {[s.decode('mbcs','replace') for _, s, _, _ in info['modules']]}")
    name, sname, off, mt = target

    old = _read_all(vba.OpenStream(sname, None, RWX, 0))
    if off > len(old):
        raise RuntimeError(f"MODULEOFFSET({off}) 超出流长({len(old)})")
    prefix = old[:off]

    src_bytes = source_text.encode(f"cp{cp}", "replace") if cp else source_text.encode("latin-1")
    comp, padded = compress(src_bytes)
    new_stream = prefix + comp

    ns = vba.CreateStream(sname, STGM_CREATE | RWX, 0)   # STGM_CREATE = 替换已有流
    keep.append(ns)
    ns.Write(new_stream)
    ns.Commit(0)

    # _VBA_PROJECT：Version -> 0xFFFF（长度不变，原地改写）
    vp = bytearray(_read_all(vba.OpenStream("_VBA_PROJECT", None, RWX, 0)))
    old_ver = struct.unpack_from("<H", vp, 2)[0]
    struct.pack_into("<H", vp, 2, 0xFFFF)
    vs = vba.CreateStream("_VBA_PROJECT", STGM_CREATE | RWX, 0)
    keep.append(vs)
    vs.Write(bytes(vp))
    vs.Commit(0)

    vba.Commit(0)
    for o in reversed(keep):
        try:
            o.Commit(0)
        except Exception:  # noqa: BLE001
            pass
    del ns, vs, vba, cur, stg
    del keep
    gc.collect()

    return {"out": out_path, "template": template_swp,
            "module_name": name.decode("mbcs", "replace") if name else None,
            "module_stream": sname, "module_offset": off, "module_type": hex(mt),
            "codepage": cp,
            "source_bytes": len(src_bytes), "padded_bytes": len(padded),
            "compressed_bytes": len(comp), "stream_bytes": len(new_stream),
            "old_vba_project_version": hex(old_ver),
            "new_vba_project_version": "0xFFFF"}


def verify(out_path, module_stream=None, expect_source=None):
    """读回生成物核验：结构、模块表、源码解压、_VBA_PROJECT 版本。"""
    import pythoncom
    keep = []
    stg = pythoncom.StgOpenStorage(out_path, None, RO, None, 0)
    keep.append(stg)
    cur = stg
    for name in SWP_PATH:
        cur = cur.OpenStorage(name, None, RO, None, 0)
        keep.append(cur)
    vba = cur.OpenStorage("VBA", None, RO, None, 0)
    keep.append(vba)
    res = {}
    info = parse_dir(decompress(_read_all(vba.OpenStream("dir", None, RO, 0))))
    res["codepage"] = info["codepage"]
    res["modules"] = [(n.decode("mbcs", "replace") if n else None,
                       s.decode("mbcs", "replace") if s else None, o, hex(mt))
                      for n, s, o, mt in info["modules"]]
    vp = _read_all(vba.OpenStream("_VBA_PROJECT", None, RO, 0))
    res["vba_project_version"] = hex(struct.unpack_from("<H", vp, 2)[0])
    srcs = {}
    for n, s, o, mt in info["modules"]:
        if not s:
            continue
        sn = s.decode("mbcs", "replace")
        raw = _read_all(vba.OpenStream(sn, None, RO, 0))
        try:
            srcs[sn] = decompress(raw[o:]).decode(f"cp{info['codepage']}", "replace")
        except Exception as e:  # noqa: BLE001
            srcs[sn] = f"<解压失败 {type(e).__name__}: {e}>"
    res["sources"] = srcs
    if module_stream and module_stream in srcs:
        res["target_source_ok"] = (expect_source is None) or (expect_source in srcs[module_stream])
    return res


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else "selftest"
    if cmd == "selftest":
        selftest(args[1] if len(args) > 1 else None)
    elif cmd == "dump":
        dump(args[1])
    elif cmd == "build":
        # build <模板> <模块流名|auto> <源码文件> <输出>
        tpl, mod, srcf, out = args[1], args[2], args[3], args[4]
        text = open(srcf, encoding="utf-8").read()
        r = build_swp(tpl, text, out, None if mod == "auto" else mod)
        print("build:", r)
        print("verify:", verify(out, r["module_stream"], "Sub main()")["modules"])
    else:
        print(__doc__)
