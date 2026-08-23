from shuddhi import pii


def test_email():
    assert pii.scan("contact us at support@example.co.in for help") == {"email": 1}


def test_indian_phone():
    assert pii.scan("call +91 9876543210 today") == {"phone_in": 1}
    assert pii.scan("call 09876543210 today") == {"phone_in": 1}
    # landline-style short numbers and years must not match
    assert pii.scan("in 2026 the office had 43210 visitors") == {}


def test_aadhaar_grouped_only():
    assert pii.scan("aadhaar 1234 5678 9012 on file") == {"aadhaar": 1}
    # unspaced 12-digit runs are NOT claimed as aadhaar (too FP-prone)
    assert "aadhaar" not in pii.scan("order id 123456789012 shipped")


def test_pan():
    assert pii.scan("PAN ABCDE1234F provided") == {"pan": 1}
    assert pii.scan("pan abcde1234f lowercase") == {}  # PAN is printed uppercase


def test_card_requires_luhn():
    assert pii.scan("card 4111 1111 1111 1111 charged") == {"card": 1}  # Luhn-valid
    assert "card" not in pii.scan("ref 4111 1111 1111 1112 logged")     # Luhn-invalid


def test_ip():
    assert pii.scan("server at 192.168.1.10 responded") == {"ip": 1}


def test_clean_text():
    assert pii.scan("The monsoon arrived early this year across the coast.") == {}


def test_redact_replaces_and_counts():
    text = "mail a@b.com or call +91 9876543210, card 4111 1111 1111 1111"
    red, counts = pii.redact(text)
    assert counts == {"email": 1, "phone_in": 1, "card": 1}
    assert "[PII:email]" in red and "[PII:phone_in]" in red and "[PII:card]" in red
    assert "a@b.com" not in red and "9876543210" not in red and "4111" not in red


def test_redact_full_doc_beyond_scan_probe():
    text = ("x" * (pii.SCAN_PROBE_CHARS + 100)) + " a@b.com"
    assert pii.scan(text) == {}  # scan is bounded...
    red, counts = pii.redact(text)
    assert counts == {"email": 1}  # ...redaction is not
    assert "a@b.com" not in red
