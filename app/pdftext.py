"""Minimal, dependency-free PDF text extraction for in-app previews.

Supports: FlateDecode streams, object streams (PDF 1.5+), ToUnicode CMaps (bfchar / bfrange),
simple and Type0 (2-byte) fonts, Tj / TJ / ' / " operators and basic line/page breaks.
It is intentionally small: when a PDF cannot be decoded the caller falls back to "download the original".
"""
from __future__ import annotations

import re
import zlib

_OBJ = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)
_REF = re.compile(rb"(\d+)\s+0\s+R")
_STREAM = re.compile(rb"stream\r?\n(.*)\r?\n?endstream", re.S)


def _inflate(data: bytes) -> bytes:
    for trim in (data, data.rstrip(b"\r\n")):
        try:
            return zlib.decompress(trim)
        except zlib.error:
            pass
    try:
        return zlib.decompressobj().decompress(data)
    except zlib.error:
        return b""


def _split(body: bytes):
    """Return (dictionary bytes, decoded stream or None)."""
    m = _STREAM.search(body)
    if not m:
        return body, None
    head, data = body[:m.start()], m.group(1)
    if b"/FlateDecode" in head:
        data = _inflate(data)
    elif b"/Filter" in head:
        data = b""
    return head, data


class _Doc:
    def __init__(self, raw: bytes):
        self.objs: dict[int, bytes] = {}
        for m in _OBJ.finditer(raw):
            self.objs[int(m.group(1))] = m.group(3)
        for num, body in list(self.objs.items()):
            if b"/ObjStm" in body[:400]:
                head, data = _split(body)
                if not data:
                    continue
                n = int((re.search(rb"/N\s+(\d+)", head) or [0, b"0"])[1])
                first = int((re.search(rb"/First\s+(\d+)", head) or [0, b"0"])[1])
                nums = data[:first].split()
                for i in range(n):
                    try:
                        onum, off = int(nums[2 * i]), int(nums[2 * i + 1])
                        end = int(nums[2 * i + 3]) if 2 * i + 3 < len(nums) else len(data) - first
                    except (IndexError, ValueError):
                        break
                    self.objs.setdefault(onum, data[first + off:first + end])

    def get(self, ref) -> bytes:
        return self.objs.get(int(ref), b"")

    def deref(self, value: bytes) -> bytes:
        m = _REF.fullmatch(value.strip())
        return self.get(m.group(1)) if m else value


def _cmap(data: bytes) -> tuple[dict[int, str], int]:
    out, width = {}, 1

    def hexval(h):
        return int(h, 16) if h else 0

    def uni(h):
        try:
            return bytes.fromhex(h.decode()).decode("utf-16-be", "ignore")
        except ValueError:
            return ""

    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block):
            width = max(width, len(src) // 2)
            out[hexval(src)] = uni(dst)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
        for a, b, rest in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]*>)", block):
            width = max(width, len(a) // 2)
            lo, hi = hexval(a), hexval(b)
            if rest.startswith(b"["):
                for i, d in enumerate(re.findall(rb"<([0-9A-Fa-f]*)>", rest)):
                    out[lo + i] = uni(d)
            else:
                base = rest.strip(b"<>")
                start = hexval(base)
                n = max(1, len(base) // 2)
                for i, code in enumerate(range(lo, min(hi, lo + 4096) + 1)):
                    out[code] = uni(f"{start + i:0{n * 2}x}".encode())
    return out, width


def _unescape(s: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(s):
        ch = s[i]
        if ch == 0x5C and i + 1 < len(s):
            n = s[i + 1]
            i += 2
            if n in b"nrtbf":
                out += {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t", ord("b"): b"\b", ord("f"): b"\f"}[n]
            elif 0x30 <= n <= 0x37:
                j, v = 0, n - 0x30
                while j < 2 and i < len(s) and 0x30 <= s[i] <= 0x37:
                    v, i, j = v * 8 + s[i] - 0x30, i + 1, j + 1
                out.append(v & 0xFF)
            elif n in (0x0A, 0x0D):
                pass
            else:
                out.append(n)
            continue
        out.append(ch)
        i += 1
    return bytes(out)


_TOK = re.compile(rb"\((?:\\.|[^\\()]|\((?:\\.|[^\\()])*\))*\)|<[0-9A-Fa-f\s]*>|\[|\]|/[^\s/\[\]()<>]+|[-+]?\d*\.?\d+|[A-Za-z'\"*]+", re.S)


def _fonts(doc: _Doc, page: bytes) -> dict[bytes, tuple[dict, int]]:
    res = doc.deref((re.search(rb"/Resources\s*(\d+\s+0\s+R|<<.*>>)", page, re.S) or [b"", b""])[1]) if b"/Resources" in page else b""
    fm = re.search(rb"/Font\s*(\d+\s+0\s+R|<<(.*?)>>)", res, re.S)
    fonts = {}
    if not fm:
        return fonts
    fdict = doc.deref(fm.group(1)) if fm.group(1).strip().endswith(b"R") and not fm.group(1).startswith(b"<<") else fm.group(1)
    for name, ref in re.findall(rb"/([^\s/<>\[\]]+)\s+(\d+)\s+0\s+R", fdict):
        fobj = doc.get(ref)
        tu = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", fobj)
        cmap, width = ({}, 2 if b"/Type0" in fobj else 1)
        if tu:
            _, data = _split(doc.get(tu.group(1)))
            if data:
                cmap, w = _cmap(data)
                width = max(width if b"/Type0" in fobj else 1, w)
        fonts[name] = (cmap, width)
    return fonts


def _decode(raw: bytes, font) -> str:
    cmap, width = font or ({}, 1)
    if not cmap:
        if width == 2:
            return raw.decode("utf-16-be", "ignore")
        return raw.decode("latin-1")
    out = []
    for i in range(0, len(raw) - width + 1, width):
        code = int.from_bytes(raw[i:i + width], "big")
        out.append(cmap.get(code, ""))
    return "".join(out)


def _content_text(data: bytes, fonts) -> str:
    lines, cur, font, last_y = [], [], None, None
    stack = []

    def flush():
        if cur:
            lines.append("".join(cur).rstrip())
            cur.clear()

    for m in _TOK.finditer(data):
        tok = m.group(0)
        if tok.startswith(b"(") or tok.startswith(b"<") or tok in (b"[", b"]") or tok.startswith(b"/") or re.match(rb"[-+]?\d*\.?\d+$", tok):
            stack.append(tok)
            continue
        op = tok
        if op == b"Tf" and len(stack) >= 2:
            font = fonts.get(stack[-2][1:])
        elif op in (b"Tj", b"'", b'"', b"TJ"):
            if op in (b"'", b'"'):
                flush()
            parts = []
            for s in stack:
                if s.startswith(b"("):
                    parts.append(_decode(_unescape(s[1:-1]), font))
                elif s.startswith(b"<"):
                    parts.append(_decode(bytes.fromhex(re.sub(rb"\s", b"", s[1:-1]).decode() + ("0" if len(re.sub(rb"\s", b"", s[1:-1])) % 2 else "")), font))
                elif op == b"TJ" and re.match(rb"[-+]?\d*\.?\d+$", s) and float(s) < -180:
                    parts.append(" ")
            cur.append("".join(parts))
        elif op in (b"Td", b"TD", b"Tm") and len(stack) >= 2:
            try:
                y = float(stack[-1])
            except ValueError:
                y = None
            if op == b"Tm":
                if last_y is not None and y is not None and abs(y - last_y) > 2:
                    flush()
                last_y = y
            elif y is not None and abs(y) > 0.5:
                flush()
            elif cur and not cur[-1].endswith(" "):
                cur.append(" ")
        elif op == b"T*":
            flush()
        elif op == b"ET":
            pass
        stack.clear()
    flush()
    dedup = []
    for line in lines:
        if not dedup or line != dedup[-1] or not line:
            dedup.append(line)
    return "\n".join(dedup)


def extract_pages(raw: bytes, max_pages: int = 30) -> list[str]:
    if not raw.startswith(b"%PDF"):
        return []
    doc = _Doc(raw)
    pages = [(n, b) for n, b in sorted(doc.objs.items()) if re.search(rb"/Type\s*/Page(?!s)", b)]
    out = []
    for _, page in pages[:max_pages]:
        fonts = _fonts(doc, page)
        cm = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+0\s+R)", page)
        refs = _REF.findall(cm.group(1)) if cm else []
        text = []
        for r in refs:
            _, data = _split(doc.get(r))
            if data:
                text.append(_content_text(data, fonts))
        page_text = re.sub(r"[ \t]+\n", "\n", "\n".join(text)).strip()
        out.append(re.sub(r"\n{3,}", "\n\n", page_text))
    return out
