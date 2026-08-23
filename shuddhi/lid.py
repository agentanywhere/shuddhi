"""Language identification — stage 2.

Primary path: fastText lid.176 (via the pip-installable `fasttext-predict`
wheel — no compiler needed), which distinguishes languages sharing a script
(hin/mar/nep/san all write Devanagari). Fallback path: Unicode-script counting,
which is dependency-free and exact about *script* but can only claim script
consistency, not language identity, for shared-script languages. Every result
records which method produced it so reports never conflate the two.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The 15 corpus languages (ISO 639-3 as used in shard names).
CORPUS_LANGS = frozenset(
    "hin nep ben tam eng tel mal mar guj urd san kan ori pan asm".split()
)

# fastText lid.176 ISO 639-1 labels -> our shard codes.
FT_TO_SHARD = {
    "hi": "hin", "ne": "nep", "bn": "ben", "ta": "tam", "en": "eng",
    "te": "tel", "ml": "mal", "mr": "mar", "gu": "guj", "ur": "urd",
    "sa": "san", "kn": "kan", "or": "ori", "pa": "pan", "as": "asm",
    # frequent near-neighbours worth naming rather than lumping into "other"
    "bh": "bho", "mai": "mai", "bpy": "bpy", "gom": "gom", "sd": "snd",
}

_SCRIPT_PATTERNS: dict[str, re.Pattern] = {
    "deva": re.compile("[ऀ-ॿ]"),
    "beng": re.compile("[ঀ-৿]"),
    "guru": re.compile("[਀-੿]"),
    "gujr": re.compile("[઀-૿]"),
    "orya": re.compile("[଀-୿]"),
    "taml": re.compile("[஀-௿]"),
    "telu": re.compile("[ఀ-౿]"),
    "knda": re.compile("[ಀ-೿]"),
    "mlym": re.compile("[ഀ-ൿ]"),
    "arab": re.compile("[؀-ۿݐ-ݿ]"),
    "latn": re.compile("[A-Za-z]"),
}

# Scripts that map to exactly one corpus language.
_SCRIPT_TO_LANG = {
    "guru": "pan", "gujr": "guj", "orya": "ori", "taml": "tam",
    "telu": "tel", "knda": "kan", "mlym": "mal", "arab": "urd",
    "latn": "eng",
}
# Scripts shared by several corpus languages — script ID alone cannot pick one.
SCRIPT_SHARED_LANGS = {
    "deva": frozenset({"hin", "mar", "nep", "san"}),
    "beng": frozenset({"ben", "asm"}),
}

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class LidResult:
    lang: str | None      # shard-code language, or None if undetermined
    script: str | None    # dominant script
    confidence: float     # model confidence (fasttext) or script char share
    method: str           # "fasttext" | "script"

    def consistent_with(self, shard_lang: str) -> bool:
        """Is this result consistent with the shard's language tag?

        fasttext: exact language match. script: the dominant script must be
        one the shard language writes in (the honest claim script ID can make).
        """
        if self.method == "fasttext":
            return self.lang == shard_lang
        if self.script is None:
            return False
        if self.script in SCRIPT_SHARED_LANGS:
            return shard_lang in SCRIPT_SHARED_LANGS[self.script]
        return _SCRIPT_TO_LANG.get(self.script) == shard_lang


def dominant_script(text: str, probe_chars: int = 2000) -> tuple[str | None, float]:
    """Dominant Unicode script of the first `probe_chars` chars and its share
    of script-bearing characters."""
    probe = text[:probe_chars]
    counts = {s: len(p.findall(probe)) for s, p in _SCRIPT_PATTERNS.items()}
    total = sum(counts.values())
    if total == 0:
        return None, 0.0
    script = max(counts, key=counts.get)  # ties: dict order, deterministic
    return script, counts[script] / total


class ScriptLID:
    """Dependency-free fallback: identifies script, and language only where the
    script is unambiguous."""

    method = "script"

    def identify(self, text: str) -> LidResult:
        script, share = dominant_script(text)
        lang = _SCRIPT_TO_LANG.get(script) if script else None
        return LidResult(lang=lang, script=script, confidence=share, method="script")


class FastTextLID:
    """fastText lid.176 wrapper (fasttext-predict wheel)."""

    method = "fasttext"

    def __init__(self, model_path: str):
        import fasttext  # fasttext-predict installs under this name

        self._model = fasttext.load_model(model_path)
        self._script_fallback = ScriptLID()

    def identify(self, text: str, probe_chars: int = 400) -> LidResult:
        probe = _WS.sub(" ", text[:probe_chars]).strip()
        if not probe:
            return LidResult(None, None, 0.0, "fasttext")
        labels, probs = self._model.predict(probe, k=1)
        if not labels:
            return LidResult(None, None, 0.0, "fasttext")
        iso = labels[0].replace("__label__", "")
        lang = FT_TO_SHARD.get(iso, iso)  # keep the raw ISO code for "other" breakdown
        script, _ = dominant_script(text)
        return LidResult(lang=lang, script=script, confidence=float(probs[0]), method="fasttext")


def make_lid(model_path: str | None):
    """Best available LID: fasttext when a model file is supplied and loadable,
    otherwise script counting. Returns (lid, method_name)."""
    if model_path:
        try:
            lid = FastTextLID(model_path)
            return lid, lid.method
        except Exception:
            pass
    lid = ScriptLID()
    return lid, lid.method
