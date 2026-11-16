"""engine.py — Azerbaijani-aware text utilities, PII masking, transliteration."""
import pytest

from app import engine


# ---------------------------------------------------------------- casing / folding / tokens
def test_az_lower_handles_dotted_and_dotless_i():
    assert engine.az_lower("İSTİ Ilıq") == "isti ılıq"
    assert engine.az_lower("ABC") == "abc"


def test_fold_removes_diacritics():
    assert engine.fold("Müqavimət Şəbəkə Çöl Ğ") == "muqavimet sebeke col g"


def test_tokens_latin_cyrillic_and_digits():
    assert engine.tokens("Om qanunu, 12 V!") == ["om", "qanunu", "12", "v"]
    assert engine.tokens("Справка для банка") == ["справка", "для", "банка"]
    assert engine.tokens("") == []


@pytest.mark.parametrize("a, b", [
    ("müqavimət", "müqavimətlərin"), ("dövr", "dövrlərdə"), ("cərəyan", "cərəyanda"), ("Kirxhof", "Kirxhofun"),
    ("gərginlik", "gərginliyin"), ("kitab", "kitablar"),
])
def test_stem_maps_inflected_forms_to_the_same_stem(a, b):
    assert engine.stem(engine.tokens(a)[0]) == engine.stem(engine.tokens(b)[0])


def test_stem_keeps_numbers_and_short_words():
    assert engine.stem("12") == "12"
    assert engine.stem("evdən") == "evden"           # too short for suffix stripping
    assert engine.stem("evlərdən") == "evler"        # case suffix removed, plural kept (stem would get too short)
    assert len(engine.stem("elektromaqnetizm")) == 5  # truncated to 5 characters


def test_terms_drops_stop_words_and_single_letters_but_keeps_digits():
    assert engine.terms("Om qanunu nədir və 5 V?") == ["om", "qanun", "5"]
    assert engine.terms("the a an is", drop_stop=True) == []
    assert "the" in engine.terms("the law", drop_stop=False)


# ---------------------------------------------------------------- markdown helpers
MD = """# Başlıq

## Om qanunu
> I = U / R

- **Cərəyan şiddəti** — vahid zamanda keçən yükün miqdarıdır. Gərginlik artır! Sonra?
`kod` və **qalın**

```python
print(1)
```
"""


def test_plain_strips_light_markdown():
    p = engine.plain(MD)
    assert "```" not in p and "print(1)" not in p
    assert "**" not in p and "`" not in p
    assert "# " not in p and "> " not in p
    assert "Cərəyan şiddəti — vahid zamanda" in p


def test_split_sentences_skips_headings_quotes_and_code():
    s = engine.split_sentences(MD)
    assert s[0] == "Cərəyan şiddəti — vahid zamanda keçən yükün miqdarıdır."
    assert "Gərginlik artır!" in s and "Sonra?" in s
    assert not any(x.startswith("#") or x.startswith(">") or "print" in x for x in s)


def test_formulas_and_code_blocks():
    assert engine.formulas(MD) == ["I = U / R"]
    assert engine.code_blocks(MD) == ["print(1)"]
    assert engine.code_blocks("no code") == []


# ---------------------------------------------------------------- privacy
def test_mask_pii_detects_phone_fin_email_and_card():
    text, found = engine.mask_pii("FİN: 5ABC12D, tel +994 50 123 45 67, e-poçt aysel@example.az, kart 4169 7388 1234 5678")
    assert found == ["E-POÇT", "TELEFON", "KART", "FİN"]
    assert "[TELEFON]" in text and "[FİN]" in text and "[E-POÇT]" in text and "[KART]" in text
    assert "5ABC12D" not in text and "example.az" not in text and "4169" not in text


def test_mask_pii_leaves_plain_text_alone():
    text, found = engine.mask_pii("Om qanunu nədir? 12 V və 4 Ω")
    assert found == [] and text == "Om qanunu nədir? 12 V və 4 Ω"


def test_mask_pii_does_not_treat_course_codes_as_fin():
    # a 7-character token with letters AND digits looks like a FIN; plain words or plain numbers must not
    assert engine.mask_pii("ELM2105")[1] == ["FİN"]
    assert engine.mask_pii("ABCDEFG 1234567")[1] == []


# ---------------------------------------------------------------- transliteration & similarity
@pytest.mark.parametrize("az, en", [
    ("Aysel Məmmədova", "Aysel Mammadova"), ("Elçin Quliyev", "Elchin Guliyev"), ("Xəyal Cəfərov", "Khayal Jafarov"),
    ("Günel Şükürova", "Gunel Shukurova"), ("İlqar Ağayev", "Ilgar Aghayev"),
])
def test_translit_passport_style(az, en):
    assert engine.translit(az) == en


def test_similarity_is_jaccard_on_stems():
    assert engine.similarity("Om qanunu nədir?", "Om qanununu izah et") == 1.0
    assert engine.similarity("Om qanunu", "Kirxhof qanunu") == pytest.approx(1 / 3)
    assert engine.similarity("", "x") == 0.0
