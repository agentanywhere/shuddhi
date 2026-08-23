"""Domain classifier v1 — stage 5. Keyword/heuristic tiers.

Buckets: coding / bfsi / reasoning / indic / general, assigned by precedence
(coding > bfsi > reasoning > language). "indic" means Indic-language content
that is not one of the specialist domains; "general" is the same for English.
Language comes from the LID stage, so domain × language is reported as a
matrix and the two axes never get conflated.

This is a v1 keyword classifier — good for corpus-level composition numbers,
not for per-document routing. Signals are counted as *distinct* pattern hits
so one repeated word cannot fake a domain.
"""

from __future__ import annotations

import re

DOMAINS = ("coding", "bfsi", "reasoning", "indic", "general")

_CODE_SIGNALS = [
    re.compile(p)
    for p in (
        r"\bdef [a-z_]+\(", r"\bfunction\s*[a-zA-Z_]*\(", r"\bclass\s+[A-Z]\w*",
        r"\bimport\s+[a-z_.]+", r"#include\s*<", r"\bpublic\s+static\b",
        r"console\.log", r"\bSELECT\b.{1,80}\bFROM\b", r"</[a-z]+>",
        r"=>", r"\breturn\b.{0,40};", r"\bnull\b|\bNone\b|\bnullptr\b",
        r"[{}();]\s*\n\s*[{}();]",
    )
]

_BFSI_TERMS = (
    # English
    "bank", "banking", "loan", "credit", "debit", "insurance", "premium",
    "mutual fund", "rbi", "sebi", "irdai", "emi", "fixed deposit",
    "interest rate", "kyc", "upi", "neft", "rtgs", "imps", "ifsc", "demat",
    "nbfc", "repo rate", "savings account", "current account", "net banking",
    "policyholder", "underwriting", "actuarial", "collateral", "disbursement",
    # Hindi/Devanagari
    "बैंक", "ऋण", "ब्याज", "बीमा", "प्रीमियम", "किस्त", "खाता", "भुगतान",
    "निवेश", "शेयर बाजार", "म्यूचुअल फंड", "जमा", "कर्ज", "पॉलिसी",
)
_BFSI_PATTERNS = [re.compile(re.escape(t), re.IGNORECASE) for t in _BFSI_TERMS]
BFSI_MIN_DISTINCT = 3

_REASONING_SIGNALS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\btheorem\b", r"\bproof\b", r"\blemma\b", r"\bequation\b",
        r"\bprobability\b", r"\balgorithm\b", r"\bsolve for\b",
        r"\bstep \d\b", r"\btherefore\b", r"[∴∵∑∫√≤≥≠]",
        r"\d\s*[+\-×*/=]\s*\d", r"\bq\.?e\.?d\b", r"प्रमेय", r"समीकरण", r"हल कीजिए",
    )
]
REASONING_MIN_DISTINCT = 2

PROBE_CHARS = 4000
INDIC_LANGS = frozenset(
    "hin nep ben tam tel mal mar guj urd san kan ori pan asm".split()
)


def classify(text: str, lang: str | None) -> str:
    """Classify one document. `lang` is the LID result (shard code or None)."""
    probe = text[:PROBE_CHARS]

    code_hits = sum(1 for p in _CODE_SIGNALS if p.search(probe))
    if code_hits >= 2:
        return "coding"

    bfsi_hits = sum(1 for p in _BFSI_PATTERNS if p.search(probe))
    if bfsi_hits >= BFSI_MIN_DISTINCT:
        return "bfsi"

    reasoning_hits = sum(1 for p in _REASONING_SIGNALS if p.search(probe))
    if reasoning_hits >= REASONING_MIN_DISTINCT:
        return "reasoning"

    if lang in INDIC_LANGS:
        return "indic"
    return "general"
