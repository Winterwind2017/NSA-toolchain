"""DXF 读写：**无损直通**模型（算法/格式处理参照 CADCraft `crates/dxf`）。

为什么不用 ezdxf：它把 DXF 归一到自己的模型，**未知实体直接丢**——
而"读别人的图"最关键的就是别丢东西。这里的做法是：

* 解析成有序组码对 `(code, value)`，按 SECTION 分段，原样保存；
* 提供 `entities` 索引（类型/句柄/图层/坐标）方便查询与判据；
* 写回时**逐对重放**（可替换某段），未识别的实体/表项原样保留；
* 任何畸形输入（奇数行、非数字组码、二进制 DXF）都抛 `DxfError`，不猜。

已知限制（写在这，不藏）：
* 只做 ASCII DXF；二进制 DXF（"AutoCAD Binary DXF"）明确拒绝；
* 不解释 OBJECTS 段的语义，只搬运；
* 编码按 cp1252/utf-8 探测，中文图纸（ANSI_936）可能需调用方给 encoding。
"""

from __future__ import annotations

import io
import math
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Pair = Tuple[int, str]

# 常见实体里我们真正会读的 group code（其余原样留着）
TYPE_CODE = 0
HANDLE_CODE = 5
LAYER_CODE = 8
OWNER_CODE = 330
SUBCLASS_CODE = 100

FLOAT_CODES = set(range(10, 60)) | set(range(140, 150)) | {210, 220, 230, 1010, 1020, 1030}
INT_CODES = (set(range(60, 80)) | set(range(170, 180)) | set(range(270, 290))
             | set(range(370, 390)) | set(range(400, 410)) | {90, 91, 92, 93, 94, 95,
                                                                 96, 97, 98, 99})


class DxfError(ValueError):
    """DXF 结构错误（奇数行/坏组码/不支持的子格式）。"""


@dataclass
class Entity:
    type: str
    pairs: List[Pair]

    def get(self, code: int) -> Optional[str]:
        for c, v in self.pairs:
            if c == code:
                return v
        return None

    def get_all(self, code: int) -> List[str]:
        return [v for c, v in self.pairs if c == code]

    @property
    def handle(self) -> Optional[str]:
        return self.get(HANDLE_CODE)

    @property
    def layer(self) -> Optional[str]:
        return self.get(LAYER_CODE)

    def floats(self, code: int) -> List[float]:
        out = []
        for v in self.get_all(code):
            try:
                out.append(float(v))
            except ValueError:
                raise DxfError("组码 %d 的值不是数值：%r" % (code, v)) from None
        return out

    def point(self) -> Optional[Tuple[float, float, float]]:
        xs, ys, zs = self.floats(10), self.floats(20), self.floats(30)
        if not xs or not ys:
            return None
        return (xs[0], ys[0], zs[0] if zs else 0.0)

    def signature(self) -> Tuple:
        """用于比对的轻量签名（类型/句柄/图层/坐标）。"""
        return (self.type, self.handle or "", self.layer or "",
                self.point() or ())


@dataclass
class Document:
    pairs: List[Pair]                      # 全文，按顺序
    encoding: str = "utf-8"
    sections: Dict[str, List[Pair]] = field(default_factory=dict)

    # ── 查询 ──
    def entities(self, type_: Optional[str] = None) -> List[Entity]:
        out: List[Entity] = []
        for ent in _split_entities(self.sections.get("ENTITIES") or []):
            if type_ is None or ent.type == type_:
                out.append(ent)
        return out

    def layers(self) -> Dict[str, Dict[str, Optional[str]]]:
        """从 TABLES 段抽图层名与颜色/线型（没 TABLES 就返回空）。"""
        out: Dict[str, Dict[str, Optional[str]]] = {}
        tables = self.sections.get("TABLES") or []
        in_layer_table = False
        current: Optional[Dict[str, Optional[str]]] = None
        for code, value in tables:
            if code == 0 and value == "TABLE":
                in_layer_table = False
            elif code == 2 and value == "LAYER":
                in_layer_table = True
            elif code == 0 and value == "ENDTAB":
                in_layer_table = False
            elif code == 0 and value == "LAYER" and in_layer_table:
                current = {"name": None, "color": None, "linetype": None}
            elif current is not None and in_layer_table:
                if code == 2:
                    current["name"] = value
                    out[value] = current
                elif code == 62:
                    current["color"] = value
                elif code == 6:
                    current["linetype"] = value
        return out

    def acadver(self) -> Optional[str]:
        header = self.sections.get("HEADER") or []
        for i, (code, value) in enumerate(header):
            if code == 9 and value == "$ACADVER":
                if i + 1 < len(header) and header[i + 1][0] == 1:
                    return header[i + 1][1]
        return None


def _split_entities(pairs: Sequence[Pair]) -> List[Entity]:
    out: List[Entity] = []
    cur: Optional[Entity] = None
    for code, value in pairs:
        if code == 0:
            if cur is not None:
                out.append(cur)
            cur = Entity(value, [(code, value)])
        elif cur is not None:
            cur.pairs.append((code, value))
    if cur is not None:
        out.append(cur)
    return out


# ── 读 ──────────────────────────────────────────────────────────────
def read(path: str, *, encoding: Optional[str] = None) -> Document:
    if not os.path.isfile(path):
        raise DxfError("文件不存在：%s" % path)
    raw = open(path, "rb").read()
    if raw[:22].startswith(b"AutoCAD Binary DXF"):
        raise DxfError("二进制 DXF 不支持（只做 ASCII）")
    text = None
    for enc in ([encoding] if encoding else ["utf-8", "cp1252", "latin-1"]):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        raise DxfError("无法解码（给 encoding 参数再试）")

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) % 2 != 0:
        raise DxfError("行数为奇数（组码/值不成对），文件可能被截断")
    pairs: List[Pair] = []
    for i in range(0, len(lines), 2):
        code_s = lines[i].strip()
        try:
            code = int(code_s)
        except ValueError:
            raise DxfError("第 %d 行不是组码：%r" % (i + 1, lines[i][:40])) from None
        pairs.append((code, lines[i + 1].rstrip()))
    return Document(pairs=pairs, encoding=encoding or "utf-8", sections=_sections(pairs))


def _sections(pairs: Sequence[Pair]) -> Dict[str, List[Pair]]:
    out: Dict[str, List[Pair]] = {}
    i = 0
    while i < len(pairs):
        code, value = pairs[i]
        if code == 0 and value == "SECTION":
            name = pairs[i + 1][1] if i + 1 < len(pairs) and pairs[i + 1][0] == 2 else ""
            body: List[Pair] = []
            j = i + 2
            while j < len(pairs) and not (pairs[j][0] == 0 and pairs[j][1] == "ENDSEC"):
                body.append(pairs[j])
                j += 1
            out[name] = body
            i = j + 1
            continue
        i += 1
    return out


# ── 写 ──────────────────────────────────────────────────────────────
def write(doc: Document, path: str) -> Dict[str, object]:
    """逐对重放写回（无损）。返回字节数以便判据。"""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        raise DxfError("父目录不存在：%s" % d)
    buf = io.StringIO()
    for code, value in doc.pairs:
        buf.write("%d\n%s\n" % (code, value))
    data = buf.getvalue().encode(doc.encoding if doc.encoding != "utf-8" else "utf-8",
                                 errors="replace")
    with open(path, "wb") as fh:
        fh.write(data)
    return {"path": path, "bytes": len(data), "pairs": len(doc.pairs)}


def new_document(acadver: str = "AC1032") -> Document:
    """最小的合法 DXF（HEADER + TABLES 空 + ENTITIES 空）。"""
    pairs: List[Pair] = [(0, "SECTION"), (2, "HEADER"), (9, "$ACADVER"), (1, acadver),
                         (0, "ENDSEC"),
                         (0, "SECTION"), (2, "TABLES"), (0, "ENDSEC"),
                         (0, "SECTION"), (2, "ENTITIES"), (0, "ENDSEC"),
                         (0, "EOF")]
    return Document(pairs=pairs, sections=_sections(pairs))


def add_entity(doc: Document, entity: Entity) -> None:
    """把实体插进 ENTITIES 段末尾（在 ENDSEC 之前）。"""
    idx = None
    for i, (code, value) in enumerate(doc.pairs):
        if code == 0 and value == "ENDSEC":
            # 找到 ENTITIES 段的 ENDSEC：它前面最近的 SECTION 名是 ENTITIES
            for j in range(i - 1, -1, -1):
                if doc.pairs[j][0] == 0 and doc.pairs[j][1] == "SECTION":
                    if j + 1 < len(doc.pairs) and doc.pairs[j + 1] == (2, "ENTITIES"):
                        idx = i
                    break
            if idx is not None:
                break
    if idx is None:
        raise DxfError("文档里没有 ENTITIES 段")
    doc.pairs[idx:idx] = list(entity.pairs)
    doc.sections = _sections(doc.pairs)


def make_line(p1: Tuple[float, float], p2: Tuple[float, float],
              layer: str = "0", handle: str = "1") -> Entity:
    return Entity("LINE", [
        (0, "LINE"), (5, handle), (100, "AcDbEntity"), (8, layer),
        (100, "AcDbLine"),
        (10, _fmt(p1[0])), (20, _fmt(p1[1])), (30, "0.0"),
        (11, _fmt(p2[0])), (21, _fmt(p2[1])), (31, "0.0"),
    ])


def make_circle(center: Tuple[float, float], radius: float,
                layer: str = "0", handle: str = "2") -> Entity:
    return Entity("CIRCLE", [
        (0, "CIRCLE"), (5, handle), (100, "AcDbEntity"), (8, layer),
        (100, "AcDbCircle"),
        (10, _fmt(center[0])), (20, _fmt(center[1])), (30, "0.0"),
        (40, _fmt(radius)),
    ])


def _fmt(v: float) -> str:
    return ("%.10g" % float(v))


def length(p1, p2) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])
