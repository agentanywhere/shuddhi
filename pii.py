"""PII detection + redaction — the rights/privacy stage (§5 of the DeepSeek
brief lists PII/policy/rights filtering as a core data-factory stage).

Detectors are deliberately conservative, pattern-based, and documented:

  email     RFC-lite mailbox pattern
  phone_in  Indian mobile numbers (10 digits starting 6-9, optional +91/0)
  aadhaar   12 digits in the printed 4-4-4 grouping (unspaced 12-digit runs
            are far too FP-prone to claim as Aadhaar)
  pan       Indian PAN (AAAAA9999A)
  card      13-19 digit runs (with separators) that pass the Luhn check —
            the check kills invoice/order-number false positives
  ip        dotted-quad IPv4

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
    for name, pat in _PATTERNS.items():
        n = len(pat.findall(probe))
        if n:
            counts[name] = n
    n = len(_card_matches(probe))
    if n:
        counts["card"] = n
    return counts


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Replace every PII match in the FULL document with [PII:<type>].
    Returns (redacted_text, counts). Card redaction runs first so that the
    narrower number patterns cannot consume parts of a card number."""
    counts: dict[str, int] = {}

    spans = _card_matches(text)
    if spans:
        counts["card"] = len(spans)
        parts, last = [], 0
        for m in spans:
            parts.append(text[last : m.start()])
            parts.append("[PII:card]")
            last = m.end()
        parts.append(text[last:])
        text = "".join(parts)

    for name, pat in _PATTERNS.items():
        text, n = pat.subn(f"[PII:{name}]", text)
        if n:
            counts[name] = n
    return text, counts
