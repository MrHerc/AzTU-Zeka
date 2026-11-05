"""engine.py — BM25 index, markdown chunking, glossary extraction, document text extraction."""
import io
import zipfile

import pytest

from app import engine


# ---------------------------------------------------------------- BM25
@pytest.fixture
def index():
    ix = engine.BM25()
    ix.add(1, "Om qanunu: cərəyan gərginliklə düz, müqavimətlə tərs mütənasibdir.", {"course_id": 1, "heading": "Om qanunu"}, boost="Om qanunu")
    ix.add(2, "Kirxhofun birinci qanunu: düyünə daxil olan cərəyanların cəmi çıxanların cəminə bərabərdir.", {"course_id": 1, "heading": "Kirxhof"}, boost="Kirxhof")
    ix.add(3, "range() funksiyası ardıcıl tam ədədlər verir.", {"course_id": 2, "heading": "Dövrlər"}, boost="Dövrlər")
    return ix


def test_search_ranks_the_matching_passage_first(index):
    hits = index.search("Kirxhof qanunu düyün", k=3)
    assert hits[0]["id"] == 2 and hits[0]["heading"] == "Kirxhof"
    assert all(h["score"] > 0 for h in hits)
    assert [h["id"] for h in hits] == [2, 1]           # doc 3 shares no term


def test_search_results_carry_meta_and_rounded_scores(index):
    h = index.search("range funksiyası", k=1)[0]
    assert h["id"] == 3 and h["course_id"] == 2
    assert h["score"] == round(h["score"], 3)


def test_search_where_filter_and_k_limit(index):
    assert [h["id"] for h in index.search("qanunu", k=5, where=lambda m: m["course_id"] == 1)] == [1, 2] or \
           [h["id"] for h in index.search("qanunu", k=5, where=lambda m: m["course_id"] == 1)] == [2, 1]
    assert index.search("qanunu", k=1).__len__() == 1
    assert index.search("qanunu", where=lambda m: m["course_id"] == 99) == []


def test_search_empty_query_or_only_stop_words(index):
    assert index.search("") == []
    assert index.search("və bu bir") == []
    assert engine.BM25().search("om") == []


def test_heading_boost_counts_double():
    ix = engine.BM25()
    ix.add("a", "cərəyan gərginlik", boost="")
    ix.add("b", "cərəyan gərginlik", boost="Kirxhof")
    assert ix.search("Kirxhof")[0]["id"] == "b"
    assert ix.docs["b"][0][engine.stem("kirxhof")] == 2


def test_add_same_id_replaces_without_double_counting(index):
    n, total = len(index.docs), index.total_len
    index.add(1, "Om qanunu: cərəyan gərginliklə düz, müqavimətlə tərs mütənasibdir.", {"course_id": 1}, boost="Om qanunu")
    assert len(index.docs) == n and index.total_len == total
    assert index.df[engine.stem("om")] == 1


def test_remove(index):
    index.remove(2)
    index.remove(999)                                   # unknown id is a no-op
    assert 2 not in index.docs and index.search("Kirxhof") == []
    assert index.df[engine.stem("kirxhof")] == 0


# ---------------------------------------------------------------- chunking
def test_chunk_markdown_splits_on_h2_and_names_the_preamble():
    md = "# Mövzu\n\nGiriş mətni.\n\n## A bölməsi\n\nA mətni.\n\n## B bölməsi\n\nB mətni.\n"
    assert engine.chunk_markdown(md) == [("Giriş", "Giriş mətni."), ("A bölməsi", "A mətni."), ("B bölməsi", "B mətni.")]


def test_chunk_markdown_skips_empty_sections_and_only_the_first_h1():
    md = "## Boş\n\n   \n## Dolu\n\n# Sənədin adı\n\nmətn\n\n# ikinci H1 mətndə qalır"
    assert engine.chunk_markdown(md) == [("Dolu", "mətn\n\n# ikinci H1 mətndə qalır")]
    assert engine.chunk_markdown("") == []


def test_chunk_markdown_splits_long_sections_by_paragraph():
    paras = [f"Paraqraf {i} " + "söz " * 60 for i in range(6)]
    md = "## Uzun\n\n" + "\n\n".join(paras)
    parts = engine.chunk_markdown(md, max_chars=700)
    assert len(parts) >= 3
    assert [h for h, _ in parts] == [f"Uzun ({i})" for i in range(1, len(parts) + 1)]
    assert all(len(body) <= 700 + 320 for _, body in parts)           # one paragraph may overshoot
    assert "".join(p.strip() for p in paras).replace(" ", "") == "".join(b for _, b in parts).replace(" ", "").replace("\n", "")


def test_chunk_markdown_short_section_is_not_numbered():
    assert engine.chunk_markdown("## X\n\n" + "a" * 50, max_chars=100) == [("X", "a" * 50)]


# ---------------------------------------------------------------- glossary
def test_glossary_bold_and_capitalised_patterns():
    md = ("- **Transformator** — dəyişən cərəyanın gərginliyini çevirən qurğudur.\n"
          "Generator — mexaniki enerjini elektrik enerjisinə çevirən maşındır.\n"
          "- **Qısa** — qısa.\n"                 # definition too short
          "kiçik hərf — bu tərif pattern-ə uyğun deyil, çünki termin kiçik hərflə başlayır.\n")
    assert engine.glossary(md) == [
        ("Transformator", "dəyişən cərəyanın gərginliyini çevirən qurğudur."),
        ("Generator", "mexaniki enerjini elektrik enerjisinə çevirən maşındır."),
    ]


def test_glossary_on_real_material_finds_terms():
    text = (engine.ROOT / "content" / "materials" / "elm-1-om-qanunu.md").read_text(encoding="utf-8") if (engine.ROOT / "content").exists() else None
    if text is None:
        from pathlib import Path
        text = (Path(__file__).resolve().parents[2] / "content" / "materials" / "elm-1-om-qanunu.md").read_text(encoding="utf-8")
    gl = dict(engine.glossary(text))
    assert len(gl) >= 4 and all(len(d) >= 12 for d in gl.values())


# ---------------------------------------------------------------- extraction
def _docx(paragraphs):
    """Minimal .docx: [(style or None, text), ...]"""
    body = ""
    for style, text in paragraphs:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        body += f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def _pptx(slides):
    ns = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i, paras in enumerate(slides, 1):
            ps = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in paras)
            z.writestr(f"ppt/slides/slide{i}.xml", f'<p:sld {ns}><p:cSld><p:spTree><p:sp><p:txBody>{ps}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>')
    return buf.getvalue()


def test_extract_text_markdown_and_txt_with_bom_and_legacy_encoding():
    assert engine.extract_text("a.md", "﻿# Salam\n".encode("utf-8")) == "# Salam\n"
    assert engine.extract_text("a.txt", "Güç ölçüsü, ağır iş".encode("cp1254")) == "Güç ölçüsü, ağır iş"   # not valid UTF-8


def test_extract_text_docx_maps_styles_to_headings():
    data = _docx([("Title", "Elektrik dövrələri"), (None, "Giriş mətni."), ("Heading1", "Om qanunu"), (None, "I = U / R"),
                  ("Heading2", "Alt başlıq"), (None, "   "), (None, "Son")])
    text = engine.extract_text("lecture.docx", data)
    lines = [ln for ln in text.splitlines() if ln]
    assert lines == ["# Elektrik dövrələri", "Giriş mətni.", "## Om qanunu", "I = U / R", "## Alt başlıq", "Son"]


def test_extract_text_pptx_orders_slides_numerically():
    slides = [["Birinci slayd", "mətn 1"], ["İkinci", "mətn 2"]] + [[f"Slayd {i}"] for i in range(3, 12)]
    text = engine.extract_text("deck.pptx", _pptx(slides))
    assert text.startswith("## Slayd 1: Birinci slayd\nmətn 1\n")
    assert text.index("## Slayd 9:") < text.index("## Slayd 10:") < text.index("## Slayd 11:")


def test_extract_text_rejects_unknown_types():
    with pytest.raises(ValueError):
        engine.extract_text("x.pdf", b"%PDF")
    with pytest.raises(zipfile.BadZipFile):
        engine.extract_text("x.docx", b"not a zip")
