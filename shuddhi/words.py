"""The matching normal form shared by the contamination and toxicity screens.

Both screens answer "does this text contain those words?", so both need one
definition of *the same text* and of *a word*. This module is that
definition, and WORD_NORMALIZER_VERSION is its identity in receipts.

The normal form (language-neutral, Unicode-standard operations only):

  1. fold      NFKC, then casefold, then drop ignorable code points, then
               NFKC again if anything changed. This is Unicode's
               NFKC_Casefold recipe built from stdlib parts. It makes
               canonically-equivalent text compare equal — ज़ typed as U+095B
               or as ज + nukta, Bengali/Tamil/Malayalam two-part vowel signs
               typed whole or in halves, Arabic presentation forms from PDF
               extraction, the "ﬁ" ligature, full-width Latin — and removes
               characters that are invisible by design and routinely hide or
               break a match: ZWJ/ZWNJ/ZWSP, soft hyphen, bidi marks and
               embeddings (everywhere in Urdu web text), BOM, word joiner,
               variation selectors.
  2. split     a word is a maximal run of \\w and combining marks (M*) that
               contains at least one \\w character.

Why marks are word-internal: Python re's \\w does NOT match categories
Mn/Mc/Me, so the v1 splitter (\\W+) broke every Indic word at each vowel sign,
virama and nukta, and threw the marks away — मुझे became ['म', 'झ']; 7 Hindi
words became 13 consonant fragments, 6 Tamil words 19 (measured); vocalised
Urdu broke at every zabar/zer/pesh. Both sides of a screen were fragmented
alike so it still ran, but an "8-word" contamination gram covered ~4 real
words with their vowels stripped, and toxicity density was computed over ~2x
too many "words".

Deliberately NOT folded — these are language-specific spelling choices, not
Unicode equivalences, and belong in a later version if measurement shows they
matter: Arabic-script vocalisation marks and tatweel, Arabic vs Farsi yeh/kaf,
Malayalam legacy chillu sequences vs atomic chillus, nukta-less respellings
(बाजार for बाज़ार), transliteration.

Stdlib-only and deterministic. Mark and ignorable ranges come from
`unicodedata`, i.e. the interpreter's Unicode tables, exactly as \\w and NFKC
themselves do. Unicode's stability policies mean a newer table can only add
behaviour for newly assigned characters; it never changes the normal form of
text that was already assigned. The table version is recorded in every
manifest as env.unicode.

Bump WORD_NORMALIZER_VERSION on ANY change that can alter the word list
produced for some input. Contamination grams and toxicity verdicts depend on
it, FilterConfig pins it, and tests/test_words.py holds a golden digest that
fails until it is bumped.

  1  lower() + \\W+ split (through v1.2.0; never recorded in receipts)
  2  NFKC_Casefold-style fold; combining marks are word-internal
"""

from __future__ import annotations

import functools
import re
import sys
import unicodedata

WORD_NORMALIZER_VERSION = 2

# Pure-ASCII text is already in normal form apart from case, and contains no
# marks or ignorables, so the plain pattern gives the identical word list at
# a fraction of the cost. English corpora never leave this path.
_ASCII_BREAK = re.compile(r"\W+")
_HAS_WORD_CHAR = re.compile(r"\w")

_VARIATION_SELECTORS = (*range(0xFE00, 0xFE10), *range(0xE0100, 0xE01F0))
_CGJ = 0x034F  # combining grapheme joiner: a mark, but invisible by design


def _class_body(cps) -> str:
    """Code points as the body of a regex character class (ranges merged).
    Callers pass only non-ASCII code points, so nothing needs escaping."""
    ranges: list[list[int]] = []
    for cp in sorted(cps):
        if ranges and ranges[-1][1] == cp - 1:
            ranges[-1][1] = cp
        else:
            ranges.append([cp, cp])
    return "".join(chr(a) if a == b else f"{chr(a)}-{chr(b)}" for a, b in ranges)


@functools.lru_cache(maxsize=None)
def _tables() -> tuple[re.Pattern, re.Pattern, frozenset]:
    """(word-break pattern, ignorable pattern, non-\\w word-internal chars).

    One ~100 ms scan of the Unicode tables on first non-ASCII input — not at
    import, so `shuddhi --help` and English-only builds never pay for it."""
    ignorable = {_CGJ, *_VARIATION_SELECTORS}
    marks = set()
    for cp in range(0x80, sys.maxunicode + 1):
        cat = unicodedata.category(chr(cp))
        if cat == "Cf":
            ignorable.add(cp)
        elif cat[0] == "M":
            marks.add(cp)
    # Ignorables are word-internal too: fold() removes them, but split_words()
    # on unfolded text must still never break a word at a ZWJ or soft hyphen.
    internal = marks | ignorable
    return (
        re.compile(rf"[^\w{_class_body(internal)}]+"),
        re.compile(f"[{_class_body(ignorable)}]"),
        frozenset(map(chr, internal)),
    )


def word_break_pattern() -> re.Pattern:
    """Matches a maximal run of characters that are not word-internal."""
    return _tables()[0]


def fold(text: str) -> str:
    """Matching normal form of `text` (step 1 above): the result is NFKC,
    casefolded, and contains no ignorable code points."""
    if text.isascii():
        return text.lower()
    # normalize() runs Unicode's quick check itself and returns at once when
    # the text is certainly normalized (most scripts). Combining marks make
    # the answer "maybe", so Indic text always pays for one full pass.
    t = unicodedata.normalize("NFKC", text)
    folded = t.casefold()
    ignorable = _tables()[1]
    if ignorable.search(folded):
        folded = ignorable.sub("", folded)
    if folded != t:
        # casefolding or removing an ignorable can leave text denormalised
        # (a mark now adjacent to a new base). Unchanged text — the caseless
        # Indic hot path — is provably still NFKC and skips the second pass.
        folded = unicodedata.normalize("NFKC", folded)
    return folded


def split_words(text: str) -> list[str]:
    """Words of `text`, in order, characters untouched (step 2 above)."""
    if text.isascii():
        return [w for w in _ASCII_BREAK.split(text) if w]
    brk, _, internal = _tables()
    # A run made only of marks/ignorables (a stray matra after punctuation, a
    # lone ZWJ) is not a word. Only a token that STARTS with one can be such a
    # run, so the regex check runs on almost nothing.
    return [
        w for w in brk.split(text)
        if w and (w[0] not in internal or _HAS_WORD_CHAR.search(w))
    ]


def normalize_words(text: str) -> list[str]:
    """The normal form: fold, then split. What both screens compare."""
    return split_words(fold(text))
