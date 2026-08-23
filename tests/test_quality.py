from shuddhi import quality

CLEAN_PROSE = (
    "The monsoon arrived early this year across the western coast. Farmers in the "
    "region welcomed the rains after a long dry spell that had threatened the "
    "sowing season. Agricultural officers said reservoir levels were recovering "
    "steadily and that the outlook for the kharif crop had improved considerably. "
    "Local markets also reported a gradual return to normal supply conditions."
) * 3


CLEAN_HINDI = (
    "की सरकार ने किसानों के लिए नई योजना शुरू की है। इस योजना के तहत किसानों को "
    "बेहतर बीज और सिंचाई की सुविधा दी जाएगी। अधिकारियों ने बताया कि अगले महीने से "
    "पंजीकरण शुरू होगा और सभी पात्र किसान इसमें भाग ले सकेंगे। "
) * 4

CLEAN_TAMIL = (
    "இந்த ஆண்டு பருவமழை சீக்கிரமாக தொடங்கியது. விவசாயிகள் மகிழ்ச்சியுடன் "
    "விதைப்பு பணிகளை தொடங்கினர். நீர்நிலைகள் நிரம்பி வருவதாக அதிகாரிகள் "
    "தெரிவித்தனர். சந்தைகளில் விலை நிலவரம் சீராக உள்ளது. "
) * 4


def test_clean_prose_scores_high():
    q = quality.score_doc(CLEAN_PROSE)
    assert q["bucket"] == "high"
    assert q["score"] >= 0.9


def test_clean_indic_prose_scores_high():
    """Regression: combining marks (vowel matras) are not symbol noise.
    A naive [^\\w\\s] regex scored clean Hindi at symbol_ratio 0.34 and
    bucketed the whole Devanagari corpus 'medium' (caught on the first
    full-corpus run, 2026-08-10)."""
    for text in (CLEAN_HINDI, CLEAN_TAMIL):
        q = quality.score_doc(text)
        assert q["symbol_ratio"] < 0.05
        assert q["bucket"] == "high"


def test_boilerplate_is_penalized():
    boiler = (
        CLEAN_PROSE
        + " Subscribe to our newsletter. Click here to read more. "
        + "All rights reserved. Privacy policy. Advertisement. Follow us. "
        + "Download our app. Sign up today. Cookie settings."
    )
    q = quality.score_doc(boiler)
    assert q["boilerplate_hits"] >= 5
    assert q["score"] < quality.score_doc(CLEAN_PROSE)["score"]


def test_repeated_lines_are_penalized():
    doc = "buy cheap widgets online today\n" * 40
    q = quality.score_doc(doc)
    assert q["dup_line_frac"] > 0.9
    assert q["score"] < 0.75


def test_short_docs_are_capped():
    q = quality.score_doc("A tiny fragment.")
    assert q["score"] <= quality.CAP_SHORT
    assert q["bucket"] == "low"


def test_symbol_spam_penalized():
    doc = ("@@## $$%% ^^&& **(( ))!! ~~|| " + CLEAN_PROSE[:100]) * 10
    q = quality.score_doc(doc)
    assert q["symbol_ratio"] > quality.SYMBOL_RATIO_MAX
    assert q["score"] < quality.score_doc(CLEAN_PROSE)["score"]


def test_bucket_edges():
    assert quality.bucket_for(0.75) == "high"
    assert quality.bucket_for(0.5) == "medium"
    assert quality.bucket_for(0.49) == "low"
