"""Token accounting — measured bytes/token per language with OUR tokenizer.

Token counts for a 176 GB corpus cannot be measured exhaustively on a small
CPU box, so the factory measures the bytes/token ratio of each shard on a
deterministic sub-sample using the trained Tatva 32k tokenizer
(paramanu/nano/tokenizer.json) and derives the shard estimate as
raw_bytes × tokens/byte. Both the measured sample (bytes, tokens) and the
derived estimate are reported separately — the estimate is always labelled
as such. This mirrors and refines the corpus-wide 3.9 bytes/token measurement
from TATVA-ASSETS.md with a per-language ratio.
"""

from __future__ import annotations


class TokenRatioMeter:
    """Accumulates (utf-8 bytes, tokens) over sampled docs up to a byte budget."""

    def __init__(self, tokenizer_path: str, byte_budget: int = 30_000_000):
        from tokenizers import Tokenizer

        self._tok = Tokenizer.from_file(tokenizer_path)
        self.byte_budget = byte_budget
        self.sampled_bytes = 0
        self.sampled_tokens = 0
        self.sampled_docs = 0

    @property
    def full(self) -> bool:
        return self.sampled_bytes >= self.byte_budget

    def add(self, text: str) -> None:
        if self.full:
            return
        self.sampled_bytes += len(text.encode("utf-8"))
        self.sampled_tokens += len(self._tok.encode(text).ids)
        self.sampled_docs += 1

    def summary(self, shard_bytes: int) -> dict:
        ratio = self.sampled_bytes / self.sampled_tokens if self.sampled_tokens else None
        return {
            "measured_docs": self.sampled_docs,
            "measured_bytes": self.sampled_bytes,
            "measured_tokens": self.sampled_tokens,
            "bytes_per_token": round(ratio, 4) if ratio else None,
            "estimated_shard_tokens": int(shard_bytes / ratio) if ratio else None,
        }
