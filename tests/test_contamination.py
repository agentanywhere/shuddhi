from shuddhi.contamination import EvalSetIndex, normalize_words

EVAL_PROMPT = (
    "There is a bug in src/orders.js. findOrder crashes with a TypeError when "
    "the id is not present. Fix it. Do not change anything else."
)


def make_index():
    return EvalSetIndex(
        [
            {"id": "bug-fix", "text": EVAL_PROMPT},
            {"id": "short-item", "text": "make both tests pass"},
        ]
    )


def test_clean_doc_no_hits():
    idx = make_index()
    doc = (
        "The monsoon arrived early this year across the western coast and farmers "
        "welcomed the rains after a long dry spell that threatened the sowing season."
    )
    assert idx.check_doc(doc) == []


def test_verbatim_prompt_inside_doc_is_caught():
    idx = make_index()
    doc = "Here is a tutorial I found online. " + EVAL_PROMPT + " Good luck with the exercise!"
    hits = idx.check_doc(doc)
    kinds = {h["kind"] for h in hits}
    assert {h["eval_id"] for h in hits} == {"bug-fix"}
    assert "exact" in kinds or "near" in kinds


def test_partial_gram_overlap_is_caught():
    idx = make_index()
    # 8+ consecutive words lifted from the prompt, rest is new text.
    doc = (
        "Someone posted: findOrder crashes with a TypeError when the id is not "
        "present, and asked how to debug it in general."
    )
    hits = idx.check_doc(doc)
    assert hits and hits[0]["eval_id"] == "bug-fix"
    assert hits[0]["kind"] == "near"


def test_punctuation_and_case_do_not_hide_contamination():
    idx = make_index()
    doc = "FINDORDER crashes, with a TYPEERROR — when the ID is not present!!!"
    # normalization: lowercase + strip punctuation; the 8-gram survives
    hits = idx.check_doc(doc)
    assert hits and hits[0]["eval_id"] == "bug-fix"


def test_short_eval_items_do_not_false_positive_via_grams():
    idx = make_index()
    # "make both tests pass" is <40 normalized chars and <8 words: it must not
    # fire the exact-substring detector on ordinary text that includes it.
    doc = "To fix CI you usually just make both tests pass and push again."
    assert all(h["eval_id"] != "short-item" for h in idx.check_doc(doc))


def test_normalize_words():
    assert normalize_words("Fix it. Do NOT change anything-else!") == [
        "fix", "it", "do", "not", "change", "anything", "else",
    ]
