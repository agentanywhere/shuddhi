"""Toxicity / unsafe-content screening — lexicon tier (v1.2).

A public data factory cannot ship without a safety screen. This is the
lexicon tier: per-language term lists matched on word boundaries, scored as
distinct-term hits + density over a bounded probe. It catches overtly
abusive/adult documents; it is NOT a classifier and does not understand
context (that is the documented v2 upgrade — a distilled classifier hook).

The built-in lists are deliberately small, unambiguous starters (English +
Hindi/Devanagari + romanized-Hindi). Production deployments should mount
fuller per-language lexicons (e.g. the AI4Bharat abuse lists, license
permitting) via `--toxicity-lexicon-dir`: one <lang>.txt per language, one
lowercase term per line, '#' comments allowed. External lists are sha-pinned
into the stats/filter config so a build states exactly which lexicon
screened it.

Scoring: a document is flagged when it has >= MIN_DISTINCT distinct toxic
terms AND hit density >= MIN_DENSITY (hits per word on the probe). Both
thresholds are deliberately conservative: this stage exists to drop the
unambiguous tail, not to adjudicate borderline text.
"""

from __future__ import annotations

import hashlib
import os
import re

PROBE_CHARS = 6000
MIN_DISTINCT = 2
MIN_DENSITY = 0.004  # 1 hit per 250 words

# Small, unambiguous starter lists. Curated for precision over recall:
# every term is unambiguous profanity/abuse in its language.
_BUILTIN: dict[str, tuple[str, ...]] = {
    "eng": (
        "fuck", "fucking", "motherfucker", "shit", "bullshit", "asshole",
        "bitch", "bastard", "cunt", "dick", "cock", "pussy", "slut", "whore",
        "faggot", "nigger", "nigga", "retard", "rape", "rapist",
        "porn", "porno", "xxx", "blowjob", "handjob", "gangbang",
    ),
    "hin": (
        "मादरचोद", "भोसड़ी", "भोसडी", "चूतिया", "चुतिया", "गांडू", "गांड",
        "रंडी", "हरामी", "हरामखोर", "कमीना", "कुतिया", "लौड़ा", "लौड़े",
        "झाटू", "बहनचोद", "बलात्कार",
    ),
    "hin-latn": (
        "madarchod", "bhosdi", "bhosdike", "chutiya", "chutiye", "gandu",
        "randi", "harami", "haramkhor", "kutiya", "lauda", "laude", "jhatu",
        "behenchod", "bhenchod",
    ),
}


_SPLIT = re.compile(r"\W+", re.UNICODE)


class ToxicityLexicon:
    """Matching is word-set membership, not one giant alternation regex: the
    probe is split on non-word chars (same boundary semantics as (?<!\\w)term
    (?!\\w) — 'shitake'/'Scunthorpe' cannot match) and each word is a C-speed
    frozenset lookup. Measured on the first v1.2 production build: the regex
    version cost ~1–2 ms/doc and dominated build time; this is ~50 µs/doc.
    Multi-word terms from external lexicons keep a small alternation regex —
    the builtin starter has none, so the common path never runs a regex scan.
    """

    def __init__(self, terms_by_lang: dict[str, tuple[str, ...]], source: str):
        self.source = source
        all_terms = sorted({t.lower() for terms in terms_by_lang.values() for t in terms if t})
        self.n_terms = len(all_terms)
        self._words = frozenset(t for t in all_terms if not _SPLIT.search(t))
        multi = [t for t in all_terms if _SPLIT.search(t)]
        self._multi_rx = (
            re.compile(
                r"(?<!\w)(?:" + "|".join(re.escape(t) for t in multi) + r")(?!\w)",
                re.IGNORECASE | re.UNICODE,
            )
            if multi else None
        )
        # sha over the sorted term list — matcher implementation is not part
        # of the lexicon identity
        self.sha256 = hashlib.sha256(
            "\n".join(all_terms).encode("utf-8")
        ).hexdigest()

    @classmethod
    def builtin(cls) -> "ToxicityLexicon":
        return cls(_BUILTIN, "builtin-starter")

    @classmethod
    def from_dir(cls, lexicon_dir: str) -> "ToxicityLexicon":
        """Load <lang>.txt files; merged WITH the builtin starter lists."""
        terms: dict[str, tuple[str, ...]] = dict(_BUILTIN)
        for fn in sorted(os.listdir(lexicon_dir)):
            if not fn.endswith(".txt"):
                continue
            lang = fn[:-4]
            with open(os.path.join(lexicon_dir, fn), encoding="utf-8") as f:
                rows = tuple(
                    line.strip().lower()
                    for line in f
                    if line.strip() and not line.startswith("#")
                )
            terms[lang] = tuple(sorted(set(terms.get(lang, ())) | set(rows)))
        return cls(terms, f"builtin+{lexicon_dir}")

    def score(self, text: str) -> dict:
        probe = text[:PROBE_CHARS].lower()
        words = _SPLIT.split(probe)
        n_words = max(1, len(words))
        tox = self._words
        n_hits = 0
        distinct_hits: set[str] = set()
        for w in words:
            if w in tox:
                n_hits += 1
                distinct_hits.add(w)
        if self._multi_rx is not None:
            for m in self._multi_rx.findall(probe):
                n_hits += 1
                distinct_hits.add(m.lower())
        density = n_hits / n_words
        return {
            "hits": n_hits,
            "distinct": len(distinct_hits),
            "density": density,
            "flagged": len(distinct_hits) >= MIN_DISTINCT and density >= MIN_DENSITY,
        }
