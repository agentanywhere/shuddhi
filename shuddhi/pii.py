"""PII detection + redaction — the rights/privacy stage (§5 of the DeepSeek
brief lists PII/policy/rights filtering as a core data-factory stage).

Detectors are deliberately conservative, pattern-based, and documented.
Structured identifiers are validated by their own checksum, not just matched
by shape, so invoice and order numbers do not masquerade as PII:

  email     RFC-lite mailbox pattern
  card      13-19 digit runs (with separators) that pass the Luhn check
  iban      International Bank Account Number, validated by its ISO 13616
            mod-97 check digits (covers EU/UK/EEA account numbers)
  ip        dotted-quad IPv4
  phone_in  Indian mobile numbers (10 digits starting 6-9, optional +91/0)
  aadhaar   Indian Aadhaar, 12 digits in the printed 4-4-4 grouping
  pan       Indian PAN (AAAAA9999A)

email, card, iban and ip are region-neutral; phone_in, aadhaar and pan are
India-specific and simply find nothing in a corpus that has none. Add
region packs (national IDs, other IBAN-less account formats) as filter
plugins.

`scan()` counts occurrences (measurement); `redact()` replaces each match
with a typed placeholder like [PII:email] (applied builds). Counting is done
on a bounded probe per document so scan cost is O(1); redaction always
processes the full document, because a partially-redacted doc is worse than
an unredacted one you know about.

This is pattern-level PII screening for corpus hygiene — it is not, and does
not claim to be, a compliance-grade DLP system. Names/addresses (NER-class
detection) are v2.
"""

from __future__ import annotations

import re

SCAN_PROBE_CHARS = 8000

_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}\b", re.IGNORECASE),
    "phone_in": re.compile(r"(?<![\d\w])(?:\+91[\s-]?|0)?[6-9]\d{9}(?!\d)"),
    # exactly three 4-digit groups: reject when another 4-digit group precedes
    # or follows (that shape is a 16+ digit card number, not an Aadhaar)
    "aadhaar": re.compile(r"(?<!\d)(?<!\d[\s-])\d{4}[\s-]\d{4}[\s-]\d{4}(?![\s-]?\d)"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "ip": re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"),
}
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
# country(2) + check(2) + 11..30 alnum, tolerating the printed grouping.
_IBAN_CANDIDATE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _iban_ok(compact: str) -> bool:
    """ISO 13616 mod-97: move the first four chars to the end, map letters to
    10..35, read as one integer, and require a remainder of 1. Random 34-char
    strings pass ~1 in 97, so paired with the structural pattern the false-
    positive rate is negligible."""
    if not (15 <= len(compact) <= 34):
        return False
    rearranged = compact[4:] + compact[:4]
    try:
        n = int("".join(str(int(c, 36)) for c in rearranged))
    except ValueError:
        return False
    return n % 97 == 1


def _iban_matches(text: str) -> list[re.Match]:
    out = []
    for m in _IBAN_CANDIDATE.finditer(text):
        if _iban_ok(re.sub(r"\s", "", m.group())):
            out.append(m)
    return out


def _card_matches(text: str) -> list[re.Match]:
    out = []
    for m in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"[ -]", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            out.append(m)
    return out


def scan(text: str) -> dict[str, int]:
    """Count PII occurrences by type on a bounded probe. Types with zero hits
    are omitted."""
    probe = text[:SCAN_PROBE_CHARS]
    counts: dict[str, int] = {}
    iban_spans = _iban_matches(probe)
    if iban_spans:
        counts["iban"] = len(iban_spans)
    # a mostly-digit IBAN body can also satisfy the card Luhn shape; the IBAN
    # owns those characters, so drop card hits that overlap an IBAN.
    taken = [(m.start(), m.end()) for m in iban_spans]
    cards = [m for m in _card_matches(probe)
             if not any(a < m.end() and m.start() < b for a, b in taken)]
    if cards:
        counts["card"] = len(cards)
    for name, pat in _PATTERNS.items():
        n = len(pat.findall(probe))
        if n:
            counts[name] = n
    return counts


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Replace every PII match in the FULL document with [PII:<type>].
    Returns (redacted_text, counts). Card redaction runs first so that the
    narrower number patterns cannot consume parts of a card number."""
    counts: dict[str, int] = {}

    def replace_spans(text: str, spans: list, label: str) -> str:
        if not spans:
            return text
        counts[label] = len(spans)
        parts, last = [], 0
        for m in spans:
            parts.append(text[last : m.start()])
            parts.append(f"[PII:{label}]")
            last = m.end()
        parts.append(text[last:])
        return "".join(parts)

    # validated identifiers first, longest-structure first, so a narrower
    # number pattern cannot consume part of an IBAN or a card number.
    text = replace_spans(text, _iban_matches(text), "iban")
    text = replace_spans(text, _card_matches(text), "card")

    for name, pat in _PATTERNS.items():
        text, n = pat.subn(f"[PII:{name}]", text)
        if n:
            counts[name] = n
    return text, counts
