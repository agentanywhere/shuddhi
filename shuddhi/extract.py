"""Extraction stage — raw HTML -> blank-line-separated shard text (v1.2).

Lets the factory ingest crawls directly instead of requiring pre-extracted
text. Uses trafilatura when installed (the quality option — boilerplate
removal, main-content detection); otherwise falls back to a dependency-free
tag-stripper that is honest about being crude (scripts/styles removed, tags
stripped, whitespace collapsed). The stats record which extractor ran, so a
registry entry for an extracted shard can cite it.

Input: a directory of .html/.htm files (one document each).
Output: one shard .txt in the factory's blank-line-separated format +
<out>.extract.json with per-file accounting.
"""

from __future__ import annotations

import json
import os
import re

_SCRIPT_STYLE = re.compile(r"<(script|style|noscript)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_ENTITY = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n{2,}")

_ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " "}


def _decode_entity(m: re.Match) -> str:
    body = m.group(1)
    try:
        if body.startswith("#x") or body.startswith("#X"):
            return chr(int(body[2:], 16))
        if body.startswith("#"):
            return chr(int(body[1:]))
    except ValueError:
        return m.group(0)
    return _ENTITIES.get(body.lower(), m.group(0))


def strip_tags(html: str) -> str:
    """Crude fallback extractor: tags out, entities decoded, whitespace sane."""
    text = _SCRIPT_STYLE.sub(" ", html)
    text = _COMMENT.sub(" ", text)
    text = _TAG.sub(" ", text)
    text = _ENTITY.sub(_decode_entity, text)
    text = _WS.sub(" ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(ln for ln in lines if ln)
    return text.strip()


def extract_text(html: str) -> tuple[str, str]:
    """Returns (text, extractor_name)."""
    try:
        import trafilatura

        text = trafilatura.extract(html, include_comments=False)
        if text:
            return text.strip(), "trafilatura"
    except ImportError:
        pass
    return strip_tags(html), "strip-tags-fallback"


def extract_dir(in_dir: str, out_path: str, min_chars: int = 80) -> dict:
    files = sorted(
        fn for fn in os.listdir(in_dir) if fn.lower().endswith((".html", ".htm"))
    )
    kept = 0
    skipped_short = 0
    extractors: set[str] = set()
    # newline="" keeps Python from translating "\n" to "\r\n" on Windows:
    # a corpus written with CRLF is one this tool's own reader would have to
    # normalise back, and the file should be identical on every platform.
    with open(out_path, "w", encoding="utf-8", newline="") as out:
        for fn in files:
            with open(os.path.join(in_dir, fn), encoding="utf-8", errors="replace") as f:
                html = f.read()
            text, extractor = extract_text(html)
            extractors.add(extractor)
            # a document must not contain the record separator
            text = _BLANKS.sub("\n", text)
            if len(text) < min_chars:
                skipped_short += 1
                continue
            out.write(text + "\n\n")
            kept += 1
    stats = {
        "input_files": len(files),
        "documents_written": kept,
        "skipped_short": skipped_short,
        "min_chars": min_chars,
        "extractors_used": sorted(extractors),
    }
    with open(out_path + ".extract.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=1)
    return stats
