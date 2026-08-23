from shuddhi.toxicity import ToxicityLexicon

CLEAN_EN = (
    "The monsoon arrived early this year across the western coast and farmers "
    "welcomed the rains after a long dry spell that had threatened the season."
)
CLEAN_HI = "आज मौसम बहुत अच्छा है और बच्चे बाहर खेल रहे हैं। किसान खुश हैं।"
TOXIC_EN = "fuck this shit, what an asshole thing to say, total bullshit rant"
TOXIC_HI = "यह आदमी चूतिया है और वह रंडी हरामी भी।"


def test_clean_text_not_flagged():
    lex = ToxicityLexicon.builtin()
    assert not lex.score(CLEAN_EN)["flagged"]
    assert not lex.score(CLEAN_HI)["flagged"]


def test_toxic_english_flagged():
    r = ToxicityLexicon.builtin().score(TOXIC_EN)
    assert r["distinct"] >= 3 and r["flagged"]


def test_toxic_hindi_flagged():
    r = ToxicityLexicon.builtin().score(TOXIC_HI)
    assert r["distinct"] >= 2 and r["flagged"]


def test_single_profanity_in_long_text_not_flagged():
    # one swear in an otherwise normal document must NOT nuke the doc
    text = CLEAN_EN * 5 + " damn shit happens. " + CLEAN_EN * 5
    assert not ToxicityLexicon.builtin().score(text)["flagged"]


def test_word_boundaries():
    # substrings inside clean words must not match ("class", "assessment", "Scunthorpe")
    text = "the class assessment in scunthorpe shitake... analysis of assets"
    r = ToxicityLexicon.builtin().score(text)
    assert r["hits"] == 0


def test_external_lexicon_merges_and_pins_sha(tmp_path):
    (tmp_path / "eng.txt").write_text("# comment\nzorbleflax\n")
    lex = ToxicityLexicon.from_dir(str(tmp_path))
    builtin = ToxicityLexicon.builtin()
    assert lex.n_terms == builtin.n_terms + 1
    assert lex.sha256 != builtin.sha256
    r = lex.score("total zorbleflax nonsense, what a zorbleflax, fucking zorbleflax")
    assert r["flagged"]


def test_sha_deterministic():
    assert ToxicityLexicon.builtin().sha256 == ToxicityLexicon.builtin().sha256


def test_multiword_external_terms_still_match(tmp_path):
    (tmp_path / "eng.txt").write_text("zorble flax\n")
    lex = ToxicityLexicon.from_dir(str(tmp_path))
    r = lex.score("total zorble flax nonsense, more zorble flax, fucking zorble flax")
    assert r["hits"] >= 3 and r["flagged"]


def test_fast_path_speed():
    """The matcher must be set-lookup fast (launch-blocking perf fix:
    the alternation-regex version cost ~1-2 ms/doc on production builds)."""
    import time

    lex = ToxicityLexicon.builtin()
    doc = (CLEAN_EN + " ") * 40  # ~6000 chars, fills the probe
    lex.score(doc)  # warm
    t0 = time.perf_counter()
    for _ in range(200):
        lex.score(doc)
    per_doc = (time.perf_counter() - t0) / 200
    assert per_doc < 0.001, f"{per_doc*1e3:.2f} ms/doc — fast path regressed"
