"""The matching normal form (words.py): NFKC_Casefold-style fold, then a
split in which combining marks are word-internal.

Through v1.2.0 the splitter was \\W+, and Python's \\w does not match Mn/Mc
marks — every Indic word broke at each matra. These tests pin real word
counts for the languages the corpus is built for, and the encoding variants
of one text that must compare equal.
"""

import hashlib
import re

import pytest

from shuddhi.contamination import EvalSetIndex, GRAM_WORDS
from shuddhi.words import (
    WORD_NORMALIZER_VERSION,
    fold,
    normalize_words,
    split_words,
    word_break_pattern,
)

# (language, sentence with native punctuation, expected words)
SAMPLES = [
    (
        "hin",
        "मुझे आज बाज़ार से ताज़ी सब्ज़ियाँ खरीदनी हैं।",
        ["मुझे", "आज", "बाज़ार", "से", "ताज़ी", "सब्ज़ियाँ", "खरीदनी", "हैं"],
    ),
    (
        "mar",
        "मला आज बाजारातून ताजी भाजी आणायची आहे, कारण पाहुणे येणार आहेत.",
        ["मला", "आज", "बाजारातून", "ताजी", "भाजी", "आणायची", "आहे",
         "कारण", "पाहुणे", "येणार", "आहेत"],
    ),
    (
        "tam",
        "எனக்கு இன்று சந்தையில் காய்கறிகள் வாங்க வேண்டும்.",
        ["எனக்கு", "இன்று", "சந்தையில்", "காய்கறிகள்", "வாங்க", "வேண்டும்"],
    ),
    (
        "tel",
        "నాకు ఈరోజు మార్కెట్ నుండి కూరగాయలు కొనాలి!",
        ["నాకు", "ఈరోజు", "మార్కెట్", "నుండి", "కూరగాయలు", "కొనాలి"],
    ),
    (
        "urd",
        "مجھے آج بازار سے تازہ سبزیاں خریدنی ہیں۔",
        ["مجھے", "آج", "بازار", "سے", "تازہ", "سبزیاں", "خریدنی", "ہیں"],
    ),
    (
        # vocalised Urdu: pesh / zabar are category Mn
        "urd-vocalised",
        "مُجھے آج بازار سے سَبزیاں خریدنی ہیں۔",
        ["مُجھے", "آج", "بازار", "سے", "سَبزیاں", "خریدنی", "ہیں"],
    ),
]


@pytest.mark.parametrize("lang,text,expected", SAMPLES, ids=[s[0] for s in SAMPLES])
def test_indic_and_urdu_word_counts(lang, text, expected):
    words = normalize_words(text)
    assert len(words) == len(expected)
    assert words == expected  # marks are kept, not just "not split on"


@pytest.mark.parametrize("lang,text,expected", SAMPLES, ids=[s[0] for s in SAMPLES])
def test_old_splitter_really_fragmented_these(lang, text, expected):
    # documents the bug: guards against "fixing" the samples into ones the
    # old \W+ splitter would also have handled
    if lang == "urd":
        pytest.skip("unvocalised Urdu has no combining marks")
    old = [w for w in re.split(r"\W+", text.lower()) if w]
    assert len(old) > len(expected)


def test_vowel_signs_distinguish_words():
    # v1 reduced both to the consonant skeleton ['म', 'र']
    assert normalize_words("मेरा") == ["मेरा"]
    assert normalize_words("मेरा") != normalize_words("मारा")


# (what, variant A, variant B) — one text, two encodings. All escapes are
# explicit: several of these characters are invisible in an editor.
SAME_TEXT = [
    ("nukta precomposed vs decomposed", "बा\u095bार", "बाज\u093cार"),
    ("ZWJ inside a conjunct", "क्\u200dष", "क्ष"),
    ("ZWNJ inside a Perso-Arabic compound", "می\u200cخواہم", "میخواہم"),
    ("Bengali two-part vowel sign", "ক\u09cb", "ক\u09c7\u09be"),
    ("Tamil two-part vowel sign", "க\u0bca", "க\u0bc6\u0bbe"),
    ("Malayalam two-part vowel sign", "ക\u0d4a", "ക\u0d46\u0d3e"),
    ("Arabic presentation forms (PDF extraction)", "\ufe8f\ufe8e\ufe9d", "\u0628\u0627\u062c"),
    ("bidi embedding around Urdu", "\u202bبازار\u202c", "بازار"),
    ("left-to-right / right-to-left marks", "بازار\u200f \u200eGST", "بازار GST"),
    ("soft hyphen", "conta\u00admination", "contamination"),
    ("zero-width space", "conta\u200bmination", "contamination"),
    ("byte-order mark", "\ufeffhello", "hello"),
    ("fi ligature", "\ufb01nd", "find"),
    ("full-width Latin", "\uff27\uff33\uff34", "gst"),
    ("German sharp s under casefold", "Stra\u00dfe", "STRASSE"),
    ("emoji variation selector", "ok \u2764\ufe0f ok", "ok \u2764 ok"),
]


@pytest.mark.parametrize("what,a,b", SAME_TEXT, ids=[t[0] for t in SAME_TEXT])
def test_encoding_variants_of_one_text_compare_equal(what, a, b):
    assert a != b  # the raw strings really do differ
    assert normalize_words(a) == normalize_words(b)
    assert normalize_words(a)  # and neither vanished


def test_fold_is_idempotent():
    for text in [s[1] for s in SAMPLES] + [a for _, a, _ in SAME_TEXT] + ["ǅ ᾳ ΐ İstanbul"]:
        assert fold(fold(text)) == fold(text)


def test_split_never_breaks_at_an_ignorable_even_unfolded():
    # split_words() on text nobody folded must still not reintroduce the bug
    assert split_words("क्\u200dष") == ["क्\u200dष"]
    assert split_words("conta\u00admination") == ["conta\u00admination"]


def test_a_run_of_only_marks_is_not_a_word():
    assert normalize_words("राम ।\u093e सीता") == ["राम", "सीता"]   # stray matra
    assert normalize_words("राम \u200d सीता") == ["राम", "सीता"]    # lone ZWJ
    assert normalize_words("\u093eराम") == ["\u093eराम"]            # has letters: kept


def test_spelling_choices_are_not_folded():
    """The documented limit: these are different spellings, not different
    encodings, and v2 deliberately treats them as different words."""
    assert normalize_words("بازار") != normalize_words("بَازار")      # vocalisation
    assert normalize_words("بازار") != normalize_words("بـازار")      # tatweel
    assert normalize_words("बाज़ार") != normalize_words("बाजार")      # nukta dropped
    assert normalize_words("كي") != normalize_words("کی")            # Arabic vs Farsi kaf/yeh


def test_punctuation_still_breaks_words():
    assert normalize_words("राम।श्याम॥सीता—गीता") == ["राम", "श्याम", "सीता", "गीता"]
    assert normalize_words("Fix it. Do NOT change anything-else!") == [
        "fix", "it", "do", "not", "change", "anything", "else",
    ]


def test_ascii_fast_path_matches_wide_pattern():
    text = "The quick_brown fox: 42 jumps -- over the lazy dog's back?"
    assert text.isascii()
    assert split_words(text) == [w for w in word_break_pattern().split(text) if w]


def test_mixed_script_document():
    assert normalize_words("GST का रिटर्न 2026 में file करें") == [
        "gst", "का", "रिटर्न", "2026", "में", "file", "करें",
    ]


def test_deterministic():
    text = " ".join(s[1] for s in SAMPLES)
    assert normalize_words(text) == normalize_words(text)


def test_golden_output_is_pinned_to_the_normalizer_version():
    """If this fails you changed what the normaliser outputs. That changes
    contamination grams and toxicity verdicts for existing corpora: bump
    WORD_NORMALIZER_VERSION in words.py, add the new digest here, and note it
    in CHANGELOG.md. Do not just update the digest."""
    golden = {
        2: "cc7c95663877b16cd85bc92f9f0eda0ff42f641b5c8ab75f7dba493d765e2137",
    }
    texts = [s[1] for s in SAMPLES] + [t for _, a, b in SAME_TEXT for t in (a, b)]
    blob = "\n".join("|".join(normalize_words(t)) for t in texts)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    assert golden[WORD_NORMALIZER_VERSION] == digest


# --- contamination on Indic text -------------------------------------------

HI_ITEM = "मुझे आज बाज़ार से ताज़ी सब्ज़ियाँ खरीदनी हैं और फिर घर लौटना है"


def test_hindi_gram_is_eight_real_words():
    idx = EvalSetIndex([{"id": "hi-1", "text": HI_ITEM}])
    lifted = " ".join(HI_ITEM.split()[2:2 + GRAM_WORDS])
    hits = idx.check_doc(f"किसी ने लिखा: {lifted} — और बात खत्म।")
    assert [h["eval_id"] for h in hits] == ["hi-1"]
    assert hits[0]["kind"] == "near"
    assert hits[0]["gram"].split() == lifted.split()
    assert len(hits[0]["gram"].split()) == GRAM_WORDS


def test_five_shared_hindi_words_are_not_an_eight_gram():
    # v1 fragmented these 5 shared words into 9 pieces — enough for a false
    # "8-word" hit. Five words is below the gram size and must not fire.
    idx = EvalSetIndex([{"id": "hi-1", "text": HI_ITEM}])
    doc = "मुझे आज बाज़ार से ताज़ी हवा में घूमना अच्छा लगा क्योंकि मौसम सुहाना था"
    assert idx.check_doc(doc) == []


@pytest.mark.parametrize("lang,text,expected", SAMPLES, ids=[s[0] for s in SAMPLES])
def test_verbatim_item_is_caught_in_every_language(lang, text, expected):
    item = f"{text} {text}"  # long enough for the exact detector (>= 40 chars)
    idx = EvalSetIndex([{"id": lang, "text": item}])
    hits = idx.check_doc(f"prefix text {item} suffix text")
    assert {h["eval_id"] for h in hits} == {lang}


# --- receipts pin the normaliser --------------------------------------------

def test_filter_config_identity_includes_the_normalizer_version(monkeypatch):
    import json

    from shuddhi import builder
    from shuddhi.builder import FilterConfig

    cfg = FilterConfig()
    canonical = json.loads(cfg.canonical())
    assert canonical["scorer_params"]["word_normalizer_version"] == WORD_NORMALIZER_VERSION
    before = cfg.sha256()
    monkeypatch.setattr(builder, "WORD_NORMALIZER_VERSION", WORD_NORMALIZER_VERSION + 1)
    assert FilterConfig().sha256() != before


# --- keeping the bug from coming back ----------------------------------------

def test_no_other_module_splits_words_on_non_word_chars():
    """\\W does not know about combining marks. Anything that needs words must
    use shuddhi.words; a private \\W splitter is how v1 went wrong, twice."""
    import ast
    import pathlib

    import shuddhi

    offenders = []
    for path in pathlib.Path(shuddhi.__file__).parent.glob("*.py"):
        if path.name == "words.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "re"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and "\\W" in node.args[0].value
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
