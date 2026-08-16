import lid

HINDI = "भारत एक विशाल देश है और यहाँ अनेक भाषाएँ बोली जाती हैं। हिंदी उनमें से एक प्रमुख भाषा है।"
TAMIL = "இந்தியா ஒரு பெரிய நாடு. தமிழ் மிகப் பழமையான மொழிகளில் ஒன்று ஆகும்."
ENGLISH = "India is a large country and many languages are spoken here every single day."
BENGALI = "ভারত একটি বিশাল দেশ এবং এখানে অনেক ভাষায় কথা বলা হয়।"
URDU = "ہندوستان ایک بڑا ملک ہے اور یہاں بہت سی زبانیں بولی جاتی ہیں۔"


def test_script_lid_unambiguous_scripts():
    s = lid.ScriptLID()
    assert s.identify(TAMIL).lang == "tam"
    assert s.identify(ENGLISH).lang == "eng"
    assert s.identify(URDU).lang == "urd"


def test_script_lid_shared_scripts_stay_ambiguous():
    s = lid.ScriptLID()
    r = s.identify(HINDI)
    assert r.script == "deva"
    assert r.lang is None  # script alone cannot pick hin vs mar/nep/san
    # ...but it is consistent with any Devanagari-writing shard tag
    assert r.consistent_with("hin")
    assert r.consistent_with("nep")
    assert not r.consistent_with("tam")


def test_script_lid_bengali_covers_asm():
    r = lid.ScriptLID().identify(BENGALI)
    assert r.script == "beng"
    assert r.consistent_with("ben") and r.consistent_with("asm")
    assert not r.consistent_with("hin")


def test_make_lid_falls_back_without_model():
    l, method = lid.make_lid(None)
    assert method == "script"
    l, method = lid.make_lid("/nonexistent/model.ftz")
    assert method == "script"


def test_empty_text():
    r = lid.ScriptLID().identify("12345 !!!")
    assert r.lang is None and r.script is None
