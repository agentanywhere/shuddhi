"""IBAN detection for the European launch. Validated by the ISO 13616 mod-97
check, not shape alone, so account-number-shaped noise does not redact."""

import pytest

from shuddhi.pii import redact, scan

VALID = [
    "DE89 3704 0044 0532 0130 00",   # Germany, all-digit body
    "GB29 NWBK 6016 1331 9268 19",   # UK, letters in body
    "FR14 2004 1010 0505 0001 3M02 606",  # France, mixed
    "NL91ABNA0417164300",            # Netherlands, unspaced
]


@pytest.mark.parametrize("iban", VALID)
def test_valid_ibans_are_detected(iban):
    assert scan(iban).get("iban") == 1


def test_checksum_failure_is_not_pii():
    """One digit off must fail the mod-97 check -- the whole point of
    validating rather than matching by shape."""
    assert "iban" not in scan("DE89 3704 0044 0532 0130 01")


def test_a_plain_number_run_is_not_an_iban():
    assert "iban" not in scan("Order 4820 1002 3391 5567 shipped on Tuesday.")


def test_iban_redacts_to_a_typed_placeholder():
    text = "Wire the deposit to GB29 NWBK 6016 1331 9268 19 by Friday."
    out, counts = redact(text)
    assert "[PII:iban]" in out
    assert "NWBK" not in out
    assert counts.get("iban") == 1


def test_all_digit_iban_is_not_double_counted_as_a_card():
    """A German IBAN body is mostly digits and can satisfy the card Luhn
    shape; the IBAN owns those characters, so it must not also count as a
    card."""
    c = scan("DE89 3704 0044 0532 0130 00")
    assert c.get("iban") == 1 and "card" not in c
    out, counts = redact("Account: DE89 3704 0044 0532 0130 00")
    assert counts.get("iban") == 1 and "card" not in counts
    assert out.count("[PII:") == 1


def test_indic_patterns_still_fire_alongside():
    """Adding European detectors must not disturb the India-specific ones."""
    c = scan("PAN ABCDE1234F, Aadhaar 1234 5678 9012, mail a@b.com")
    assert c.get("pan") == 1 and c.get("aadhaar") == 1 and c.get("email") == 1
