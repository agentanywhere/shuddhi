"""Quality scoring v1 — stage 4. Heuristic, fast, and documented.

Each document gets a score in [0, 1]: start at 1.0 and subtract penalties for
measurable defects (extreme length, symbol/digit noise, repetition,
boilerplate markers). These are v1 heuristics with thresholds chosen from
inspection of Sangraha-style web text; they are reported as score
*distributions*, and the thresholds live here in one table so v1.1 can
recalibrate against a labelled sample without touching callers.

Heavy metrics are computed on a bounded prefix of the document (PROBE_CHARS /
PROBE_WORDS) so scoring cost is O(1) per document regardless of document size.
"""

from __future__ import annotations

import re
from collections import Counter

PROBE_CHARS = 4000
PROBE_WORDS = 500

_WORD_SPLIT = re.compile(r"\s+")
# Symbol noise = characters that are neither word chars, whitespace, common
# punctuation carriers, nor part of the scripts this corpus is written in.
# Python re's \w does NOT match combining marks (category Mn), so a naive
# [^\w\s] counts every Devanagari/Tamil/... vowel matra as a "symbol" and
# scores clean Indic prose as noise (measured: 0.34 on clean Hindi). The
# Indic blocks (U+0900–U+0DFF), Arabic blocks (Urdu), and ZWJ/ZWNJ are
# therefore excluded wholesale; the metric measures foreign/ASCII symbol
# spam, and script-internal punctuation (danda etc.) is deliberately not
# counted against a document.
_SYMBOL = re.compile(r"[^\w\sऀ-෿؀-ۿݐ-ݿ‌‍]", re.UNICODE)
_DIGIT = re.compile(r"\d")

# Lowercase substring markers of web boilerplate (EN + a few HI). Substring
# match, not word match — these phrases barely occur in clean prose.
BOILERPLATE_MARKERS = (
    "cookie", "subscribe", "newsletter", "all rights reserved", "copyright ©",
    "click here", "terms of service", "privacy policy", "advertisement",
    "read more", "download our app", "sign up", "log in to", "follow us",
    "whatsapp group", "telegram channel",
    "सब्सक्राइब", "विज्ञापन", "कॉपीराइट", "अस्वीकरण", "डाउनलोड करें",
)

# (penalty, reason) thresholds — the one table to recalibrate in v1.1.
SHORT_DOC_CHARS = 200      # below this a doc can score at most CAP_SHORT
CAP_SHORT = 0.30
LONG_DOC_CHARS = 500_000   # absurdly long single doc: mild penalty
SYMBOL_RATIO_MAX = 0.12
DIGIT_RATIO_MAX = 0.15
MEAN_WORD_LEN_MAX = 14.0   # URL/token spam
MEAN_WORD_LEN_MIN = 1.5
DUP_LINE_FRAC_MAX = 0.30   # within-doc repeated lines
TOP_BIGRAM_FRAC_MAX = 0.08  # single bigram dominating the text

BUCKETS = ("high", "medium", "low")


def score_doc(text: str) -> dict:
    """Return metrics + composite score + bucket for one document."""
    n_chars = len(text)
    probe = text[:PROBE_CHARS]
    words = _WORD_SPLIT.split(probe.strip())[:PROBE_WORDS]
    n_words = len(words)

    symbol_ratio = len(_SYMBOL.findall(probe)) / max(1, len(probe))
    digit_ratio = len(_DIGIT.findall(probe)) / max(1, len(probe))
    mean_word_len = sum(len(w) for w in words) / max(1, n_words)

    lines = [ln for ln in probe.splitlines() if ln.strip()]
    dup_line_frac = 1.0 - len(set(lines)) / len(lines) if len(lines) >= 5 else 0.0

    if n_words >= 20:
        bigrams = Counter(zip(words, words[1:]))
        top_bigram_frac = bigrams.most_common(1)[0][1] / max(1, n_words - 1)
    else:
        top_bigram_frac = 0.0

    lowered = probe.lower()
    boilerplate_hits = sum(1 for m in BOILERPLATE_MARKERS if m in lowered)

    score = 1.0
    if symbol_ratio > SYMBOL_RATIO_MAX:
        score -= min(0.3, (symbol_ratio - SYMBOL_RATIO_MAX) * 2.5)
    if digit_ratio > DIGIT_RATIO_MAX:
        score -= min(0.3, (digit_ratio - DIGIT_RATIO_MAX) * 2.0)
    if mean_word_len > MEAN_WORD_LEN_MAX or mean_word_len < MEAN_WORD_LEN_MIN:
        score -= 0.2
    if dup_line_frac > DUP_LINE_FRAC_MAX:
        score -= min(0.3, dup_line_frac - DUP_LINE_FRAC_MAX + 0.1)
    if top_bigram_frac > TOP_BIGRAM_FRAC_MAX:
        score -= min(0.25, (top_bigram_frac - TOP_BIGRAM_FRAC_MAX) * 2.0)
    if boilerplate_hits:
        score -= min(0.3, 0.08 * boilerplate_hits)
    if n_chars > LONG_DOC_CHARS:
        score -= 0.1
    score = max(0.0, score)
    if n_chars < SHORT_DOC_CHARS:
        score = min(score, CAP_SHORT)

    return {
        "score": round(score, 4),
        "bucket": bucket_for(score),
        "n_chars": n_chars,
        "symbol_ratio": symbol_ratio,
        "digit_ratio": digit_ratio,
        "mean_word_len": mean_word_len,
        "dup_line_frac": dup_line_frac,
        "top_bigram_frac": top_bigram_frac,
        "boilerplate_hits": boilerplate_hits,
    }


def bucket_for(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"
