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

from .words import normalize_words

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


class ToxicityLexicon:
    """Matching is word-set membership, not one giant alternation regex: the
    probe is reduced to the shared matching normal form (words.py — NFKC +
    casefold, combining marks word-internal, so a Devanagari term is ONE word,
    ज़ matches however it was typed, and 'shitake'/'Scunthorpe' cannot match)
    and each word is a C-speed frozenset lookup. Lexicon terms go through the
    same normal form, so a term and the text it should hit cannot disagree
    about spelling-level encoding.

    Measured on the first v1.2 production build: the regex version cost
    ~1–2 ms/doc and dominated build time; this is ~50 µs/doc for English.
    Multi-word terms from external lexicons are matched as word sequences,
    keyed by first word, so the common path stays a set lookup per word.

    (Through v1.2.0 the splitter was \\W+, which saw a break at every matra:
    all 17 builtin Devanagari terms fell onto a boundary-regex fallback, गांड
    matched inside गांडीव — Arjuna's bow — and density was computed over ~2x
    the true word count. Word-normalizer v2 fixed it; see words.py.)
    """

    def __init__(self, terms_by_lang: dict[str, tuple[str, ...]], source: str):
        self.source = source
        all_terms = sorted({t.lower() for terms in terms_by_lang.values() for t in terms if t})
        self.n_terms = len(all_terms)
        single: set[str] = set()
        multi: dict[str, list[tuple[str, ...]]] = {}
        for t in all_terms:
            words = tuple(normalize_words(t))
            if len(words) == 1:
                single.add(words[0])
            elif words:
                multi.setdefault(words[0], []).append(words)
        self._words = frozenset(single)
        # longest first, so "a b c" wins over "a b" at the same position
        self._multi = {k: sorted(set(v), key=len, reverse=True) for k, v in multi.items()}
        # sha over the sorted term list as written — the matcher and the
        # normal form are not part of the lexicon identity (the normal form
        # is pinned separately: FilterConfig word_normalizer_version)
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
        words = normalize_words(text[:PROBE_CHARS])
        n_words = max(1, len(words))
        tox = self._words
        multi = self._multi
        n_hits = 0
        distinct_hits: set[str] = set()
        for i, w in enumerate(words):
            if w in tox:
                n_hits += 1
                distinct_hits.add(w)
            if multi and w in multi:
                for seq in multi[w]:
                    if tuple(words[i : i + len(seq)]) == seq:
                        n_hits += 1
                        distinct_hits.add(" ".join(seq))
                        break
        density = n_hits / n_words
        return {
            "hits": n_hits,
            "distinct": len(distinct_hits),
            "density": density,
            "flagged": len(distinct_hits) >= MIN_DISTINCT and density >= MIN_DENSITY,
        }
