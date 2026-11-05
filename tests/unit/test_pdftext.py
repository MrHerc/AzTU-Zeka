"""pdftext.py — dependency-free PDF text extraction used for in-app previews of uploaded files."""
import zlib

from app import pdftext, store


def build_pdf(objects: list[bytes]) -> bytes:
    out, offsets = b"%PDF-1.5\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)


def stream(data: bytes, compress=False, extra=b"") -> bytes:
    if compress:
        data = zlib.compress(data)
        extra += b" /Filter /FlateDecode"
    return b"<< /Length %d%s >>\nstream\n" % (len(data), extra) + data + b"\nendstream"


def page_doc(content: bytes, font_obj: bytes = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", extra_objs=(), compress=False):
    return build_pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        font_obj,
        stream(content, compress),
        *extra_objs,
    ])


def test_demo_pdf_lines():
    assert pdftext.extract_pages(store.demo_pdf(["BIRINCI", "IKINCI SETIR"])) == ["BIRINCI\nIKINCI SETIR"]


def test_not_a_pdf_gives_no_pages():
    assert pdftext.extract_pages(b"PK\x03\x04 zip") == [] and pdftext.extract_pages(b"") == []


def test_flate_compressed_stream_and_escapes():
    content = b"BT /F1 12 Tf 72 700 Td (Salam \\(dunya\\) \\\\ \\101) Tj ET"
    assert pdftext.extract_pages(page_doc(content, compress=True)) == ["Salam (dunya) \\ A"]


def test_tj_arrays_insert_spaces_for_large_kerning_gaps():
    content = b"BT /F1 12 Tf 72 700 Td [(Hello) -250 (World) 30 (!)] TJ ET"
    assert pdftext.extract_pages(page_doc(content)) == ["Hello World!"]


def test_line_breaks_from_positioning_operators():
    content = b"BT /F1 12 Tf 72 700 Td (one) Tj 0 -14 Td (two) Tj T* (three) Tj ET"
    assert pdftext.extract_pages(page_doc(content)) == ["one\ntwo\nthree"]


def test_type0_font_with_tounicode_cmap():
    cmap = (b"/CIDInit /ProcSet findresource begin\nbegincmap\n1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
            b"2 beginbfchar\n<0001> <0259>\n<0002> <0041>\nendbfchar\n"
            b"1 beginbfrange\n<0010> <0012> <0061>\nendbfrange\nendcmap")
    font = b"<< /Type /Font /Subtype /Type0 /BaseFont /Inter /ToUnicode 6 0 R >>"
    content = b"BT /F1 12 Tf 72 700 Td <0002000100100011 0012> Tj ET"
    assert pdftext.extract_pages(page_doc(content, font, [stream(cmap, compress=True)])) == ["Aəabc"]


def test_bfrange_with_array_destinations():
    data, width = pdftext._cmap(b"beginbfrange\n<01> <02> [<0041> <0042>]\nendbfrange")
    assert data == {1: "A", 2: "B"} and width == 1


def test_unknown_filter_yields_empty_text_instead_of_garbage():
    pdf = build_pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>", stream(b"\x00\x01binary", extra=b" /Filter /DCTDecode"),
    ])
    assert pdftext.extract_pages(pdf) == [""]


def test_object_streams_are_unpacked():
    inner = b"3 0 4 20 "
    objs = b"<< /Type /Font /Subtype /Type1 >>   "[:20] + b"(ignored)"
    objstm = stream(inner + objs, compress=True, extra=b" /Type /ObjStm /N 2 /First %d" % len(inner))
    doc = pdftext._Doc(build_pdf([b"<< /Type /Catalog >>", objstm]))
    assert doc.get(3).startswith(b"<< /Type /Font") and doc.get(4) == b"(ignored)"


def test_page_limit_and_garbage_robustness():
    many = build_pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Count 3 >>"] +
                     [b"<< /Type /Page /Contents %d 0 R >>" % (7 + i) for i in range(3)] + [b"<< >>"] +
                     [stream(b"BT (p%d) Tj ET" % i) for i in range(3)])
    assert pdftext.extract_pages(many) == ["p0", "p1", "p2"]
    assert pdftext.extract_pages(many, max_pages=2) == ["p0", "p1"]
    assert pdftext.extract_pages(b"%PDF-1.4\n1 0 obj << /Type /Page /Contents 9 0 R >> endobj\n%%EOF") == [""]
