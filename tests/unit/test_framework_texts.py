"""The built-in frameworks' English texts are the published ones (content/frameworks/README.md, "Daxili çərçivələr").

EQF: Council Recommendation of 22 May 2017, Annex II (OJ C 189, 15.6.2017, p. 15; CELEX 32017H0615(01)), copied below
as EUR-Lex prints it: each cell starts in lower case (the row reads "The learning outcomes relevant to Level n are …")
and a cell of two statements is two paragraphs. Shown alone, a descriptor starts with a capital and its two paragraphs
are joined by "; ", as the EU's Europass page "Description of the eight EQF levels" shows them; no word changes.
Bloom: the six cognitive process categories of Anderson and Krathwohl (2001), pp. 67-68, in UK spelling (i18n/BRIEF.md).
"""
from zeka.core.i18n import S
from zeka.modules.syllabus import frameworks

ANNEX_II = (
    (["basic general knowledge"],
     ["basic skills required to carry out simple tasks"],
     ["work or study under direct supervision in a structured context"]),
    (["basic factual knowledge of a field of work or study"],
     ["basic cognitive and practical skills required to use relevant information in order to carry out tasks and to solve "
      "routine problems using simple rules and tools"],
     ["work or study under supervision with some autonomy"]),
    (["knowledge of facts, principles, processes and general concepts, in a field of work or study"],
     ["a range of cognitive and practical skills required to accomplish tasks and solve problems by selecting and applying "
      "basic methods, tools, materials and information"],
     ["take responsibility for completion of tasks in work or study",
      "adapt own behaviour to circumstances in solving problems"]),
    (["factual and theoretical knowledge in broad contexts within a field of work or study"],
     ["a range of cognitive and practical skills required to generate solutions to specific problems in a field of work or study"],
     ["exercise self-management within the guidelines of work or study contexts that are usually predictable, but are "
      "subject to change",
      "supervise the routine work of others, taking some responsibility for the evaluation and improvement of work or "
      "study activities"]),
    (["comprehensive, specialised, factual and theoretical knowledge within a field of work or study and an awareness of the "
      "boundaries of that knowledge"],
     ["a comprehensive range of cognitive and practical skills required to develop creative solutions to abstract problems"],
     ["exercise management and supervision in contexts of work or study activities where there is unpredictable change",
      "review and develop performance of self and others"]),
    (["advanced knowledge of a field of work or study, involving a critical understanding of theories and principles"],
     ["advanced skills, demonstrating mastery and innovation, required to solve complex and unpredictable problems in a "
      "specialised field of work or study"],
     ["manage complex technical or professional activities or projects, taking responsibility for decision-making in "
      "unpredictable work or study contexts",
      "take responsibility for managing professional development of individuals and groups"]),
    (["highly specialised knowledge, some of which is at the forefront of knowledge in a field of work or study, as the "
      "basis for original thinking and/or research",
      "critical awareness of knowledge issues in a field and at the interface between different fields"],
     ["specialised problem-solving skills required in research and/or innovation in order to develop new knowledge and "
      "procedures and to integrate knowledge from different fields"],
     ["manage and transform work or study contexts that are complex, unpredictable and require new strategic approaches",
      "take responsibility for contributing to professional knowledge and practice and/or for reviewing the strategic "
      "performance of teams"]),
    (["knowledge at the most advanced frontier of a field of work or study and at the interface between fields"],
     ["the most advanced and specialised skills and techniques, including synthesis and evaluation, required to solve "
      "critical problems in research and/or innovation and to extend and redefine existing knowledge or professional practice"],
     ["demonstrate substantial authority, innovation, autonomy, scholarly and professional integrity and sustained commitment "
      "to the development of new ideas or processes at the forefront of work or study contexts including research"]),
)

BLOOM = {
    "remember": ("Remember", "Retrieve relevant knowledge from long-term memory"),
    "understand": ("Understand", "Construct meaning from instructional messages, including oral, written, and graphic communication"),
    "apply": ("Apply", "Carry out or use a procedure in a given situation"),
    "analyze": ("Analyse", "Break material into its constituent parts and determine how the parts relate to one another and to "
                           "an overall structure or purpose"),
    "evaluate": ("Evaluate", "Make judgements based on criteria and standards"),
    "create": ("Create", "Put elements together to form a coherent or functional whole; reorganise elements into a new pattern "
                         "or structure"),
}


def builtin(key):
    return next(b for b in frameworks.BUILTIN if b["key"] == key)


def test_every_eqf_descriptor_is_annex_ii_word_for_word():
    items = {code: (kind, parent, text) for code, kind, parent, _, text in builtin("eqf")["items"]}
    assert len(items) == 32
    for n, row in enumerate(ANNEX_II, start=1):
        for suffix, kind, paragraphs in zip("KSR", ("knowledge", "skill", "responsibility"), row, strict=True):
            k, parent, az = items[f"{n}-{suffix}"]
            shown = "; ".join(paragraphs)
            assert (k, parent) == (kind, str(n))
            assert S(az, "en") == shown[0].upper() + shown[1:], f"{n}-{suffix}"
    assert builtin("eqf")["source_url"] == "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32017H0615(01)"
    assert [S(t, "en") for _, _, _, t, _ in builtin("eqf")["items"][::4]] == [f"Level {n}" for n in range(1, 9)]


def test_bloom_is_anderson_and_krathwohl_2001():
    got = {code: (S(title, "en"), S(text, "en")) for code, kind, _, title, text in builtin("bloom")["items"]}
    assert list(got) == list(BLOOM), "the six levels, low to high: the codes are what outcome maps point at"
    assert got == BLOOM
