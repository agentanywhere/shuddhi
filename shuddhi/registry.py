"""Shard registry + provenance ledger — stage 1 of the Tatva Data Factory.

The registry is the ONLY doorway into the factory. A shard that is not
registered, is registered with incomplete provenance, or carries a customer
data class is REFUSED before its file is ever opened. This is the mechanical
enforcement of the hard legal rule: customer data is evaluation-only, never
training. The rule lives in code, not in a memo — there is deliberately no
override flag, env var, or registry field that can admit a forbidden class.

Registry file format (JSON):

    {
      "registry_version": 1,
      "corpus_id": "tatva-sangraha-v1",
      "shards": [
        {
          "shard_id":      "sangraha_hin",
          "path":          "/abs/path/to/sangraha_hin.txt",
          "source":        "AI4Bharat Sangraha, verified subset",
          "license":       "CC-BY-4.0",
          "date_acquired": "2026-07-24",
          "data_class":    "public",
          "language":      "hin"
        }
      ]
    }

data_class semantics:
  public        — openly licensed public data (license field must say which)
  licensed      — data we hold a written license to train on
  synthetic-own — traces/text we generated ourselves on our own infra
  customer / customer-derived / evaluation-only — NEVER trainable. Refused.
  anything else / missing — refused as untagged. Refusal is the default.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from .errors import UserError

ALLOWED_DATA_CLASSES = frozenset({"public", "licensed", "synthetic-own"})
FORBIDDEN_DATA_CLASSES = frozenset({"customer", "customer-derived", "evaluation-only"})
REQUIRED_FIELDS = (
    "shard_id",
    "path",
    "source",
    "license",
    "date_acquired",
    "data_class",
    "language",
)
# Names that smell like customer/tenant material. A shard matching these while
# claiming a trainable class is refused unless a human recorded `reviewed_by`.
# The suspect check can be satisfied by review; the forbidden-class check above
# can never be.
SUSPECT_PATTERN = re.compile(
    r"customer|client|tenant|pilot|prod[-_]?log|bpo[-_]?qa|ticket", re.IGNORECASE
)


@dataclass(frozen=True)
class Shard:
    shard_id: str
    path: str
    source: str
    license: str
    date_acquired: str
    data_class: str
    language: str
    reviewed_by: str = ""

    def provenance(self) -> dict:
        return {
            "shard_id": self.shard_id,
            "source": self.source,
            "license": self.license,
            "date_acquired": self.date_acquired,
            "data_class": self.data_class,
            "language": self.language,
        }


@dataclass(frozen=True)
class Refusal:
    shard_id: str
    reason: str


def _refusal_reason(entry: dict) -> str | None:
    """Return a refusal reason for a registry entry, or None if admissible.

    Order matters: the forbidden-class check runs first and returns
    unconditionally — no later branch (including reviewed_by) is reachable
    for customer-class data.
    """
    data_class = str(entry.get("data_class", "")).strip().lower()
    if data_class in FORBIDDEN_DATA_CLASSES:
        return (
            f"data_class '{data_class}' is never trainable: customer data is "
            "evaluation-only, never training (hard legal rule; no override exists)"
        )

    missing = [f for f in REQUIRED_FIELDS if not str(entry.get(f, "")).strip()]
    if missing:
        return f"untagged shard: missing provenance field(s) {missing} — refusal is the default"

    if data_class not in ALLOWED_DATA_CLASSES:
        return (
            f"unknown data_class '{data_class}' — allowed: {sorted(ALLOWED_DATA_CLASSES)}; "
            "unknown tags are refused, not assumed"
        )

    suspect_text = f"{entry.get('shard_id', '')} {entry.get('path', '')} {entry.get('source', '')}"
    if SUSPECT_PATTERN.search(suspect_text) and not str(entry.get("reviewed_by", "")).strip():
        return (
            "suspect provenance: name/path/source matches customer-material pattern "
            f"({SUSPECT_PATTERN.pattern!r}) but claims data_class '{data_class}'. "
            "Requires a named human reviewer (`reviewed_by`) after inspection."
        )

    return None


def load_registry(path: str) -> tuple[dict, list[Shard], list[Refusal]]:
    """Load a registry file. Returns (meta, accepted shards, refusals).

    Never opens any shard file — admission is decided on the ledger alone.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        raise UserError(
            f"registry file not found: {path}",
            "Copy the example and edit the paths:\n"
            "    cp examples/registry.json my-registry.json\n"
            "Every shard needs source, license, date_acquired, data_class "
            "and language.",
        ) from None
    except IsADirectoryError:
        raise UserError(f"--registry expects a file, but {path} is a directory") from None

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UserError(
            f"{path} is not valid JSON: {e.msg} (line {e.lineno}, column {e.colno})",
            "A trailing comma or a missing quote is the usual cause.",
        ) from None
    if doc.get("registry_version") != 1:
        raise UserError(
            f"unsupported registry_version {doc.get('registry_version')!r}",
            "This build understands registry_version 1.")

    meta = {
        "corpus_id": doc.get("corpus_id", "unnamed"),
        "registry_path": path,
        "registry_sha256": hashlib.sha256(raw).hexdigest(),
    }

    accepted: list[Shard] = []
    refused: list[Refusal] = []
    seen_ids: set[str] = set()
    for entry in doc.get("shards", []):
        shard_id = str(entry.get("shard_id", "<missing shard_id>"))
        if shard_id in seen_ids:
            refused.append(Refusal(shard_id, "duplicate shard_id in registry"))
            continue
        seen_ids.add(shard_id)
        reason = _refusal_reason(entry)
        if reason is not None:
            refused.append(Refusal(shard_id, reason))
        else:
            accepted.append(
                Shard(
                    shard_id=entry["shard_id"],
                    path=entry["path"],
                    source=entry["source"],
                    license=entry["license"],
                    date_acquired=entry["date_acquired"],
                    data_class=str(entry["data_class"]).strip().lower(),
                    language=entry["language"],
                    reviewed_by=str(entry.get("reviewed_by", "")),
                )
            )
    return meta, accepted, refused
