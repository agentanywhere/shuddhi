from ngram_lm import CharTrigramLM

TRAIN = [
    "the quick brown fox jumps over the lazy dog near the quiet river bank",
    "farmers in the region welcomed the rains after a long dry spell this year",
    "the market reported a gradual return to normal supply conditions today",
] * 30


def test_in_domain_scores_lower_than_gibberish():
    lm = CharTrigramLM.train(TRAIN)
    clean = lm.bits_per_char("the farmers welcomed the quick return of the rains")
    gibberish = lm.bits_per_char("zqxj wvkp qzzt xkcv bnml pqrs zxcv qwer jklh vbnm")
    assert clean is not None and gibberish is not None
    assert clean < gibberish
    assert gibberish - clean > 1.0  # clearly separated, in bits/char


def test_short_text_unscored():
    lm = CharTrigramLM.train(TRAIN)
    assert lm.bits_per_char("hi") is None


def test_deterministic():
    a = CharTrigramLM.train(TRAIN).bits_per_char("the quick brown fox")
    b = CharTrigramLM.train(TRAIN).bits_per_char("the quick brown fox")
    assert a == b


def test_save_load_roundtrip(tmp_path):
    lm = CharTrigramLM.train(TRAIN)
    p = str(tmp_path / "test.lm.gz")
    lm.save(p)
    lm2 = CharTrigramLM.load(p)
    text = "the market welcomed the quiet river"
    assert abs(lm.bits_per_char(text) - lm2.bits_per_char(text)) < 1e-9


def test_unseen_context_backs_off():
    lm = CharTrigramLM.train(TRAIN)
    # Devanagari never seen in training: must still return a finite score
    bits = lm.bits_per_char("यह पाठ प्रशिक्षण में कभी नहीं देखा गया लेकिन स्कोर होना चाहिए")
    assert bits is not None and bits > 0
