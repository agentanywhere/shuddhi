#!/usr/bin/env python3
"""Shuddhi (शुद्धि) — Data Factory CLI.

Internal engine name: Tatva Data Factory.

Subcommands:
  doctor  Check that this Python environment can run the pipeline.
  check   Validate a shard registry: print the provenance ledger and every
          refusal. Exit 2 if anything was refused (refusal is the default
          for untagged or customer-class data).
  run     Process ONE shard end-to-end: full streaming pass (sha256, doc
          count, 64-bit doc hashes for exact dedup) + deterministic
          index-stride sample through LID, quality, domain, near-dup,
          contamination and token-ratio stages. Writes
          <out>/<shard>.hashes.u64 and <out>/<shard>.stats.json.
  merge   Combine per-shard outputs into the corpus BUILD MANIFEST:
          global exact dedup, the corpus build hash (order-independent
          blake2b over the sorted unique doc-hash set), and a composition
          summary. Writes <out>/MANIFEST.json and <out>/COMPOSITION.md.
  train-lm  Train a per-shard character-trigram LM (perplexity-proxy
          scoring) on a deterministic sample. Writes <lm-dir>/<lang>.lm.gz.
  build   Applied-filter build over a MEASURED run (run -> merge -> build):
          exact-dedup keep-first, quality threshold, per-language
          perplexity cutoff, contamination drop, PII policy. Emits a
          BUILD-MANIFEST.json whose filtered_build_hash is chained to the
          parent corpus_build_hash + the filter-config sha.

Design rule: numbers computed over the full corpus are labelled full_pass;
numbers computed on the sample carry their exact coverage. The two are never
mixed silently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from array import array
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contamination as contamination_mod
import dedup
import domain as domain_mod
import quality as quality_mod
import registry as registry_mod
import shards as shards_mod
from lid import make_lid

FACTORY_VERSION = "1.2.0"

DEFAULT_SAMPLE_EVERY = 50
DEFAULT_MINHASH_EVERY = 4
DEFAULT_TOKEN_EVERY = 20
DEFAULT_TOKEN_BYTE_BUDGET = 30_000_000
SCORE_BINS = 10
PROGRESS_EVERY = 500_000


def _env_info() -> dict:
    info = {
        "factory_version": FACTORY_VERSION,
        "python": platform.python_version(),
        "host": platform.node(),
        "git_commit": os.environ.get("FACTORY_GIT_COMMIT", ""),
    }
    for mod in ("numpy", "tokenizers"):
        try:
            info[mod] = __import__(mod).__version__
        except Exception:
            info[mod] = None
    return info


def _load_shard(registry_path: str, shard_id: str):
    meta, accepted, refused = registry_mod.load_registry(registry_path)
    for r in refused:
        if r.shard_id == shard_id:
            print(f"REFUSED {shard_id}: {r.reason}", file=sys.stderr)
            sys.exit(2)
    for s in accepted:
        if s.shard_id == shard_id:
            return meta, s
    print(f"shard {shard_id!r} not in registry {registry_path}", file=sys.stderr)
    sys.exit(2)


def cmd_report(args) -> int:
    """Draft the Article 53(1)(d) training-content summary.

    Deliberately refuses to guess: the template asks for things a corpus cannot
    know (provider identity, crawler behaviour, TDM opt-out policy) and those
    are emitted as explicit GAPs. A regulatory filing is the wrong place for a
    confident approximation.
    """
    import eu_ai_act
    if not args.eu_ai_act:
        print("report: pass --eu-ai-act (the only template supported today)")
        return 2
    meta, accepted, refused = registry_mod.load_registry(args.registry)
    manifest = eu_ai_act.load_manifest(args.manifest)
    text = eu_ai_act.build_summary(meta, accepted, refused, manifest)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out}  ({len(accepted)} shards, "
              f"{len(refused)} refused{', manifest bound' if manifest else ''})")
    else:
        print(text, end="")
    return 0


def cmd_plugins(args) -> int:
    import plugins as plugins_mod

    found = plugins_mod.available()
    if not found:
        print("no filter plugins installed.\n"
              f"Plugins register under the '{plugins_mod.ENTRY_POINT_GROUP}' "
              "entry-point group; see plugins.py and examples/plugin/.")
        return 0
    print(f"{len(found)} filter plugin(s) installed:")
    for name in sorted(found):
        try:
            inst = plugins_mod.load([name])[0]
            print(f"  {name}  v{inst.version}")
            for k, v in inst.identity().items():
                print(f"      {k}: {v}")
        except Exception as e:
            print(f"  {name}  [BROKEN: {e}]")
    print("\nEnable with: factory.py build ... --plugin <name>")
    return 0


def cmd_doctor(args) -> int:
    """Report whether this interpreter can run the pipeline, and what is
    missing. Exists because the most common failure by far is running
    factory.py with a different Python than the one the dependencies were
    installed into (system python vs venv vs conda)."""
    ok = True
    print(f"python      {platform.python_version()}  ({sys.executable})")
    if sys.version_info < (3, 10):
        print("            ERROR: Python 3.10 or newer is required")
        ok = False

    venv = os.environ.get("VIRTUAL_ENV")
    conda = os.environ.get("CONDA_DEFAULT_ENV")
    where = (f"venv: {venv}" if venv else
             f"conda env: {conda}" if conda else
             "no virtualenv/conda env active (using a system or user Python)")
    print(f"environment {where}")

    required = [("numpy", "array maths: dedup, manifests, builds")]
    optional = [
        ("tokenizers", "token accounting and the tokenizer lab", "tokens"),
        ("fasttext", "fastText language ID (else: Unicode-script fallback)", "lid"),
        ("trafilatura", "high-quality HTML extraction (else: tag-strip fallback)", "extract"),
        ("pytest", "running the test suite", "dev"),
    ]
    for mod, why in required:
        try:
            m = __import__(mod)
            print(f"  [ok]      {mod} {getattr(m, '__version__', '')} — {why}")
        except ImportError:
            print(f"  [MISSING] {mod} — {why}  (REQUIRED)")
            ok = False
    for mod, why, extra in optional:
        try:
            m = __import__(mod)
            print(f"  [ok]      {mod} {getattr(m, '__version__', '')} — {why}")
        except ImportError:
            print(f"  [absent]  {mod} — {why}  (optional: pip install '.[{extra}]')")

    print("optional data files (fetch or supply your own)")
    for path, why in (
        ("lid.176.ftz", "fastText language-ID model — `make fetch-lid`"),
        ("examples/eval-set.jsonl", "example eval set for contamination screening"),
    ):
        print(f"  [{'ok' if os.path.exists(path) else '--'}]      {path} — {why}"
              if os.path.exists(path)
              else f"  [absent]  {path} — {why}")

    if ok:
        print("\nREADY — the pipeline can run in this environment.")
    else:
        print("\nNOT READY — install the missing REQUIRED packages into THIS "
              f"interpreter:\n    {sys.executable} -m pip install -e '.[lid,tokens,extract,dev]'")
    return 0 if ok else 1


def cmd_check(args) -> int:
    meta, accepted, refused = registry_mod.load_registry(args.registry)
    print(f"registry: {meta['corpus_id']}  sha256={meta['registry_sha256'][:16]}…")
    print(f"accepted: {len(accepted)}")
    for s in accepted:
        print(f"  ✓ {s.shard_id:<16} {s.data_class:<9} {s.license:<12} {s.source}")
    print(f"refused: {len(refused)}")
    for r in refused:
        print(f"  ✗ {r.shard_id}: {r.reason}")
    return 2 if refused else 0


def cmd_run(args) -> int:
    meta, shard = _load_shard(args.registry, args.shard)
    os.makedirs(args.out, exist_ok=True)

    lid, lid_method = make_lid(args.fasttext_model)
    eval_index = None
    eval_sha = None
    if args.eval_set:
        eval_index = contamination_mod.EvalSetIndex.load(args.eval_set)
        with open(args.eval_set, "rb") as f:
            eval_sha = hashlib.sha256(f.read()).hexdigest()
    token_meter = None
    if args.tokenizer:
        from tokens import TokenRatioMeter

        token_meter = TokenRatioMeter(args.tokenizer, args.token_byte_budget)
    lm = None
    if args.lm:
        from ngram_lm import CharTrigramLM

        lm = CharTrigramLM.load(args.lm)

    near = dedup.NearDupIndex()
    sha = hashlib.sha256()
    hashes = array("Q")

    doc_bytes_total = 0
    sampled = 0
    sampled_bytes = 0
    lang_counts: Counter = Counter()
    lid_consistent = 0
    lid_conf_sum = 0.0
    q_buckets: Counter = Counter()
    q_hist = [0] * SCORE_BINS
    q_sums: Counter = Counter()
    domain_counts: Counter = Counter()
    contam_checked = 0
    contam_hits: list[dict] = []
    contam_docs_hit = 0
    token_fill_byte_depth = None
    ppx_bits = array("f")
    pii_totals: Counter = Counter()
    pii_docs = 0

    file_bytes = os.path.getsize(shard.path)
    t0 = time.time()
    cpu0 = time.process_time()
    truncated = False
    n_docs = 0

    for idx, doc in shards_mod.iter_docs(shard.path, hasher=sha):
        n_docs = idx + 1
        hashes.append(shards_mod.doc_hash64(doc))
        doc_bytes_total += len(doc)

        if idx % args.sample_every == 0:
            text = doc.decode("utf-8", "replace")
            sampled += 1
            sampled_bytes += len(doc)

            res = lid.identify(text)
            lang_counts[res.lang or "und"] += 1
            lid_conf_sum += res.confidence
            consistent = res.consistent_with(shard.language)
            if consistent:
                lid_consistent += 1
            # Language for the domain axis: prefer the LID language; when LID
            # can only vouch for the script (shared-script fallback), fall back
            # to the shard tag it is consistent with.
            effective_lang = res.lang if res.lang else (shard.language if consistent else None)

            q = quality_mod.score_doc(text)
            q_buckets[q["bucket"]] += 1
            q_hist[min(SCORE_BINS - 1, int(q["score"] * SCORE_BINS))] += 1
            for k in ("score", "symbol_ratio", "digit_ratio", "mean_word_len",
                      "dup_line_frac", "top_bigram_frac", "boilerplate_hits"):
                q_sums[k] += q[k]

            domain_counts[domain_mod.classify(text, effective_lang)] += 1

            if lm is not None:
                bits = lm.bits_per_char(text)
                if bits is not None:
                    ppx_bits.append(bits)

            if args.pii_scan:
                import pii as pii_mod

                counts = pii_mod.scan(text)
                if counts:
                    pii_docs += 1
                    pii_totals.update(counts)

            if eval_index is not None:
                hits = eval_index.check_doc(text)
                contam_checked += 1
                if hits:
                    contam_docs_hit += 1
                    for h in hits[:5]:
                        if len(contam_hits) < 100:
                            contam_hits.append({"doc_index": idx, **h})

            if sampled % args.minhash_every == 0:
                near.add(text)

            if token_meter is not None and not token_meter.full and sampled % args.token_every == 0:
                token_meter.add(text)
                if token_meter.full and token_fill_byte_depth is None:
                    token_fill_byte_depth = doc_bytes_total

        if args.max_docs and n_docs >= args.max_docs:
            truncated = True
            break

        if n_docs % PROGRESS_EVERY == 0:
            rate = doc_bytes_total / max(1e-9, time.time() - t0) / 1e6
            print(f"  {shard.shard_id}: {n_docs:,} docs, {doc_bytes_total/1e9:.1f} GB, {rate:.0f} MB/s",
                  flush=True)

    wall = time.time() - t0
    cpu = time.process_time() - cpu0

    import numpy as np

    harr = np.frombuffer(hashes, dtype=np.uint64)
    total, unique = dedup.unique_counts(harr)
    hashes_path = os.path.join(args.out, f"{shard.shard_id}.hashes.u64")
    harr.tofile(hashes_path)

    stats = {
        "shard": shard.provenance(),
        "reviewed_by": shard.reviewed_by,
        "registry_sha256": meta["registry_sha256"],
        "env": _env_info(),
        "full_pass": {
            "truncated_by_max_docs": truncated,
            "file_bytes": file_bytes,
            "file_sha256": sha.hexdigest() if not truncated else None,
            "docs": n_docs,
            "doc_bytes": doc_bytes_total,
            "exact_dup_docs": total - unique,
            "exact_dup_rate": (total - unique) / total if total else 0.0,
            "unique_docs": unique,
        },
        "sample": {
            "sample_every": args.sample_every,
            "sampled_docs": sampled,
            "sampled_doc_bytes": sampled_bytes,
            "doc_coverage": sampled / n_docs if n_docs else 0.0,
        },
        "lid": {
            "method": lid_method,
            "consistent_with_shard_tag": lid_consistent,
            "consistency_rate": lid_consistent / sampled if sampled else 0.0,
            "mean_confidence": lid_conf_sum / sampled if sampled else 0.0,
            "lang_counts": dict(lang_counts.most_common(25)),
        },
        "quality": {
            "buckets": dict(q_buckets),
            "score_histogram": q_hist,
            "means": {k: q_sums[k] / sampled for k in q_sums} if sampled else {},
        },
        "domains": dict(domain_counts),
        "near_dup": near.summary(),
        "contamination": {
            "eval_set_sha256": eval_sha,
            "docs_checked": contam_checked,
            "docs_with_hits": contam_docs_hit,
            "hits": contam_hits,
        },
        "ppx": _ppx_summary(ppx_bits, args.lm) if lm is not None else None,
        "pii": {
            "scanned_docs": sampled,
            "docs_with_pii": pii_docs,
            "counts_by_type": dict(pii_totals),
        } if args.pii_scan else None,
        "tokens": token_meter.summary(doc_bytes_total) if token_meter else None,
        "token_sample_fill_byte_depth": token_fill_byte_depth,
        "timing": {
            "wall_seconds": round(wall, 1),
            "cpu_seconds": round(cpu, 1),
            "mb_per_second": round(doc_bytes_total / 1e6 / max(1e-9, wall), 1),
        },
    }
    stats_path = os.path.join(args.out, f"{shard.shard_id}.stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    print(f"  {shard.shard_id}: DONE {n_docs:,} docs, {doc_bytes_total/1e9:.2f} GB, "
          f"dup {stats['full_pass']['exact_dup_rate']:.2%}, {wall/60:.1f} min", flush=True)
    return 0


def _ppx_summary(bits: array, lm_path: str) -> dict:
    import numpy as np

    if not len(bits):
        return {"lm": lm_path, "scored_docs": 0}
    a = np.frombuffer(bits, dtype=np.float32)
    return {
        "lm": os.path.basename(lm_path),
        "scored_docs": int(a.size),
        "mean_bits_per_char": round(float(a.mean()), 4),
        "p50": round(float(np.percentile(a, 50)), 4),
        "p90": round(float(np.percentile(a, 90)), 4),
        "p99": round(float(np.percentile(a, 99)), 4),
        "max": round(float(a.max()), 4),
    }


def cmd_train_lm(args) -> int:
    from ngram_lm import CharTrigramLM

    meta, shard = _load_shard(args.registry, args.shard)
    os.makedirs(args.lm_dir, exist_ok=True)

    texts = []
    total = 0
    budget = args.max_mb * 1_000_000
    for idx, doc in shards_mod.iter_docs(shard.path):
        if idx % args.sample_every == 0:
            texts.append(doc.decode("utf-8", "replace"))
            total += len(doc)
            if total >= budget:
                break
    lm = CharTrigramLM.train(texts)
    out = os.path.join(args.lm_dir, f"{shard.language}.lm.gz")
    lm.save(out)
    print(f"{shard.shard_id}: trained {shard.language} LM on {len(texts)} docs "
          f"({total/1e6:.1f} MB) -> {out}")
    return 0


def cmd_neardup_sig(args) -> int:
    from neardup import write_shard_sigs

    meta, shard = _load_shard(args.registry, args.shard)
    os.makedirs(args.sig_dir, exist_ok=True)
    t0 = time.time()
    stats = write_shard_sigs(shard.path, args.sig_dir, shard.shard_id)
    print(f"  {shard.shard_id}: {stats['docs']:,} docs signed "
          f"({stats['shingleable']:,} shingleable) in {(time.time()-t0)/60:.1f} min",
          flush=True)
    return 0


def cmd_neardup_merge(args) -> int:
    from neardup import merge_and_cluster

    meta, accepted, _refused = registry_mod.load_registry(args.registry)
    shard_ids = [s.shard_id for s in accepted]
    t0 = time.time()
    stats = merge_and_cluster(args.run_dir, args.sig_dir, shard_ids, args.out)
    print(f"near-dup: {stats['clusters']:,} clusters, "
          f"{stats['dropped_unique_hashes']:,} docs to drop "
          f"(largest cluster {stats['largest_cluster']:,}), "
          f"{(time.time()-t0)/60:.1f} min")
    print(f"droplist sha256: {stats['droplist_sha256']}")
    return 0


def cmd_extract(args) -> int:
    from extract import extract_dir

    stats = extract_dir(args.in_dir, args.out, min_chars=args.min_chars)
    print(json.dumps(stats, indent=1))
    return 0


def cmd_build(args) -> int:
    import numpy as np

    from builder import (DROP_REASONS, FilterConfig, HashSetIndex, build_shard,
                         filtered_build_hash)

    meta, accepted, refused = registry_mod.load_registry(args.registry)
    with open(os.path.join(args.run_dir, "MANIFEST.json"), encoding="utf-8") as f:
        parent = json.load(f)
    if parent["registry"]["sha256"] != meta["registry_sha256"]:
        print("registry file changed since the measured run — re-run measurement first",
              file=sys.stderr)
        return 2

    shard_ids = [s["shard_id"] for s in parent["shards"]]
    build_shards = [s for s in accepted if s.shard_id in shard_ids]
    if args.shards:
        wanted = set(args.shards.split(","))
        build_shards = [s for s in build_shards if s.shard_id in wanted]

    # Per-language ppx cutoffs from the measured run's percentiles. The map is
    # computed over ALL shards of the parent manifest — not just the shards
    # being built — so a partition build's filter config is identical to the
    # full build's and partition manifests union cleanly.
    max_bits: dict[str, float] = {}
    lms: dict[str, object] = {}
    if args.lm_dir:
        from ngram_lm import CharTrigramLM

        build_langs = {s.language for s in build_shards}
        for s in accepted:
            if s.shard_id not in shard_ids:
                continue
            stats_path = os.path.join(args.run_dir, f"{s.shard_id}.stats.json")
            with open(stats_path, encoding="utf-8") as f:
                st = json.load(f)
            ppx = st.get("ppx")
            lm_path = os.path.join(args.lm_dir, f"{s.language}.lm.gz")
            if ppx and ppx.get("scored_docs") and os.path.exists(lm_path):
                max_bits[s.language] = ppx[f"p{args.ppx_percentile}"]
                if s.language in build_langs and s.language not in lms:
                    lms[s.language] = CharTrigramLM.load(lm_path)

    neardup_drop = None
    neardup_sha = ""
    if args.neardup_drop:
        from neardup import droplist_sha256, load_droplist

        neardup_drop = load_droplist(args.neardup_drop)
        neardup_sha = droplist_sha256(args.neardup_drop)
    plugin_objs = []
    if args.plugin:
        import plugins as plugins_mod

        plugin_objs = plugins_mod.load(args.plugin)
        for po in plugin_objs:
            print(f"  filter plugin: {po.name} {po.version}", flush=True)

    tox_lexicon = None
    if args.toxicity:
        from toxicity import ToxicityLexicon

        tox_lexicon = (ToxicityLexicon.from_dir(args.toxicity_lexicon_dir)
                       if args.toxicity_lexicon_dir else ToxicityLexicon.builtin())

    if args.lm_dir and not max_bits:
        print("WARNING: --lm-dir was given but the measured run has no perplexity "
              "statistics, so the perplexity filter will do NOTHING. Train the "
              "language models FIRST (factory.py train-lm), then re-run "
              "`factory.py run ... --lm <lang>.lm.gz` so the distribution is "
              "measured, then build.", file=sys.stderr)

    cfg = FilterConfig(
        min_quality=args.min_quality,
        max_bits_per_char=max_bits,
        pii_policy=args.pii,
        drop_contaminated=bool(args.eval_set),
        neardup_droplist_sha256=neardup_sha,
        toxicity_lexicon_sha256=tox_lexicon.sha256 if tox_lexicon else "",
        plugin_identities=(__import__("plugins").identities(plugin_objs)
                           if plugin_objs else []),
    )
    eval_index = None
    if args.eval_set:
        eval_index = contamination_mod.EvalSetIndex.load(args.eval_set)

    os.makedirs(args.build_out, exist_ok=True)
    index = HashSetIndex.from_run_dir(args.run_dir, shard_ids)

    t0 = time.time()
    per_shard = {}
    kept_arrays = []
    for s in build_shards:  # registry order = deterministic keep-first order
        emit_path = (
            os.path.join(args.build_out, f"{s.shard_id}.filtered.txt")
            if args.emit == "text" else None
        )
        r = build_shard(s, index, cfg, lm=lms.get(s.language),
                        eval_index=eval_index, emit_path=emit_path,
                        neardup_drop=neardup_drop, tox_lexicon=tox_lexicon,
                        plugins=plugin_objs)
        kept = r.pop("kept_hashes")
        kept.tofile(os.path.join(args.build_out, f"{s.shard_id}.kept.u64"))
        kept_arrays.append(kept)
        per_shard[s.shard_id] = r
        print(f"  {s.shard_id}: kept {r['kept_docs']:,}, dropped {r['dropped']}", flush=True)

    fbh = filtered_build_hash(kept_arrays)
    total_kept = int(sum(a.size for a in kept_arrays))
    all_reasons = list(DROP_REASONS) + [f"plugin:{p.name}" for p in plugin_objs]
    dropped_by_reason = {
        reason: sum(r["dropped"].get(reason, 0) for r in per_shard.values())
        for reason in all_reasons
    }
    build_manifest = {
        "build_manifest_version": 1,
        "corpus_id": parent["corpus_id"],
        "parent_corpus_build_hash": parent["corpus_build_hash"],
        "filter_config": json.loads(cfg.canonical()),
        "filter_config_sha256": cfg.sha256(),
        "filtered_build_hash": fbh,
        "hash_definition": (
            "blake2b-256 over the ascending-sorted kept doc-hash set (same "
            "definition as the parent corpus_build_hash). Chain: parent hash + "
            "filter config sha -> this hash. Cite filtered_build_hash in the "
            "training-run ledger."
        ),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env": _env_info(),
        "shards_built": [s.shard_id for s in build_shards],
        "partial_build": len(build_shards) < len(shard_ids),
        "kept_docs": total_kept,
        "dropped_by_reason": dropped_by_reason,
        "pii_redactions": sum(r["pii_redactions"] for r in per_shard.values()),
        "per_shard": per_shard,
        "emit": args.emit,
        "wall_seconds": round(time.time() - t0, 1),
    }
    out_path = os.path.join(args.build_out, "BUILD-MANIFEST.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(build_manifest, f, ensure_ascii=False, indent=1)
    print(f"filtered_build_hash: {fbh}")
    print(f"kept {total_kept:,} docs; dropped {dropped_by_reason}")
    print(f"wrote {out_path}")
    return 0


def cmd_build_union(args) -> int:
    """Union partition builds (cmd_build with disjoint --shards run in
    parallel) into one BUILD-MANIFEST.

    Sound because the filtered_build_hash is defined over the SET of kept doc
    hashes: a cross-partition duplicate that two workers each keep collapses
    to one member in the union, so the hash is provably identical to a
    sequential build with the same config. Only the drop counters can differ
    (each such doc is counted kept-twice instead of kept+dropped-as-dup); the
    manifest records that as cross_partition_rekept_docs.
    """
    import numpy as np

    from builder import DROP_REASONS, filtered_build_hash

    parts = []
    for d in args.build_outs.split(","):
        with open(os.path.join(d, "BUILD-MANIFEST.json"), encoding="utf-8") as f:
            parts.append((d, json.load(f)))

    base = parts[0][1]
    for _, m in parts[1:]:
        for key in ("parent_corpus_build_hash", "corpus_id"):
            if m[key] != base[key]:
                print(f"partition manifests disagree on {key} — refusing to union",
                      file=sys.stderr)
                return 2

    # Filter configs must be COMPATIBLE: identical scalar filters, and
    # per-language cutoff maps that agree wherever they overlap (a partition
    # built before the invariant-map fix carries only its own languages).
    # The union config is the merged map; its sha is recomputed.
    merged_bits: dict[str, float] = {}
    for _, m in parts:
        fc = m["filter_config"]
        for key in ("min_quality", "pii_policy", "drop_contaminated", "scorer_params",
                    "neardup_droplist_sha256", "toxicity_lexicon_sha256", "plugins"):
            if fc.get(key) != base["filter_config"].get(key):
                print(f"partition filter configs disagree on {key} — refusing to union",
                      file=sys.stderr)
                return 2
        for lang, cutoff in fc.get("max_bits_per_char", {}).items():
            if lang in merged_bits and merged_bits[lang] != cutoff:
                print(f"partition cutoffs disagree for {lang!r} "
                      f"({merged_bits[lang]} vs {cutoff}) — refusing to union",
                      file=sys.stderr)
                return 2
            merged_bits[lang] = cutoff
    from builder import FilterConfig

    union_cfg = FilterConfig(
        min_quality=base["filter_config"]["min_quality"],
        max_bits_per_char=merged_bits,
        pii_policy=base["filter_config"]["pii_policy"],
        drop_contaminated=base["filter_config"]["drop_contaminated"],
        neardup_droplist_sha256=base["filter_config"].get("neardup_droplist_sha256", ""),
        toxicity_lexicon_sha256=base["filter_config"].get("toxicity_lexicon_sha256", ""),
        plugin_identities=base["filter_config"].get("plugins", []),
    )
    union_fc = json.loads(union_cfg.canonical())
    if union_fc["scorer_params"] != base["filter_config"]["scorer_params"]:
        print("scorer params in this engine version differ from the ones the "
              "partitions were built with — refusing to union", file=sys.stderr)
        return 2
    shards_seen: list[str] = []
    for _, m in parts:
        overlap = set(shards_seen) & set(m["shards_built"])
        if overlap:
            print(f"shard(s) {sorted(overlap)} appear in more than one partition — "
                  "refusing to union", file=sys.stderr)
            return 2
        shards_seen += m["shards_built"]

    arrays = []
    per_shard = {}
    for d, m in parts:
        per_shard.update(m["per_shard"])
        for sid in m["shards_built"]:
            arrays.append(np.fromfile(os.path.join(d, f"{sid}.kept.u64"), dtype=np.uint64))
    total_kept_rows = int(sum(a.size for a in arrays))
    union = np.unique(np.concatenate(arrays)) if arrays else np.empty(0, dtype=np.uint64)
    fbh = filtered_build_hash([union])

    os.makedirs(args.out, exist_ok=True)
    manifest = {
        **{k: base[k] for k in ("build_manifest_version", "corpus_id",
                                 "parent_corpus_build_hash", "hash_definition")},
        "filter_config": union_fc,
        "filter_config_sha256": union_cfg.sha256(),
        "filtered_build_hash": fbh,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env": _env_info(),
        "union_of": [d for d, _ in parts],
        "shards_built": shards_seen,
        "partial_build": any(m["partial_build"] for _, m in parts),
        "kept_docs": int(union.size),
        "cross_partition_rekept_docs": total_kept_rows - int(union.size),
        "dropped_by_reason": {
            r: sum(m["dropped_by_reason"][r] for _, m in parts) for r in DROP_REASONS
        },
        "pii_redactions": sum(m["pii_redactions"] for _, m in parts),
        "per_shard": per_shard,
        "emit": base["emit"],
    }
    out_path = os.path.join(args.out, "BUILD-MANIFEST.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"filtered_build_hash: {fbh}")
    print(f"kept {union.size:,} docs "
          f"(cross-partition re-kept: {manifest['cross_partition_rekept_docs']})")
    print(f"wrote {out_path}")
    return 0


def cmd_merge(args) -> int:
    import numpy as np

    meta, accepted, refused = registry_mod.load_registry(args.registry)

    shard_stats = {}
    missing = []
    for s in accepted:
        p = os.path.join(args.out, f"{s.shard_id}.stats.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                shard_stats[s.shard_id] = json.load(f)
        else:
            missing.append(s.shard_id)
    if missing and not args.partial:
        print(f"missing shard outputs: {missing} (use --partial to merge a subset)",
              file=sys.stderr)
        return 2

    processed = [s for s in accepted if s.shard_id in shard_stats]

    arrays = []
    for s in processed:
        arrays.append(np.fromfile(os.path.join(args.out, f"{s.shard_id}.hashes.u64"),
                                  dtype=np.uint64))
    all_hashes = np.concatenate(arrays) if arrays else np.empty(0, dtype=np.uint64)
    unique_hashes = np.unique(all_hashes)  # returned sorted
    total_docs = int(all_hashes.size)
    unique_docs = int(unique_hashes.size)
    intra_dups = sum(st["full_pass"]["exact_dup_docs"] for st in shard_stats.values())
    global_dups = total_docs - unique_docs

    build_hash = hashlib.blake2b(unique_hashes.tobytes(), digest_size=32).hexdigest()

    total_bytes = sum(st["full_pass"]["doc_bytes"] for st in shard_stats.values())
    est_tokens = 0
    tokens_known = True
    for st in shard_stats.values():
        t = st.get("tokens")
        if t and t.get("estimated_shard_tokens"):
            est_tokens += t["estimated_shard_tokens"]
        else:
            tokens_known = False

    domains: Counter = Counter()
    q_buckets: Counter = Counter()
    sampled_docs = 0
    contam_docs_hit = 0
    contam_checked = 0
    for st in shard_stats.values():
        domains.update(st["domains"])
        q_buckets.update(st["quality"]["buckets"])
        sampled_docs += st["sample"]["sampled_docs"]
        contam_docs_hit += st["contamination"]["docs_with_hits"]
        contam_checked += st["contamination"]["docs_checked"]

    manifest = {
        "manifest_version": 1,
        "corpus_id": meta["corpus_id"],
        "corpus_build_hash": build_hash,
        "build_hash_definition": (
            "blake2b-256 over the ascending-sorted set of unique 64-bit document "
            "content hashes (blake2b-8 of each blank-line-separated document, "
            "surrounding whitespace stripped) across all accepted shards. "
            "Order-independent and reproducible from the raw shard files. "
            "Every training run that consumes this corpus must cite this hash "
            "in its run ledger."
        ),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env": _env_info(),
        "registry": {"path": meta["registry_path"], "sha256": meta["registry_sha256"]},
        "provenance_gate": {
            "accepted_shards": len(processed),
            "refused": [{"shard_id": r.shard_id, "reason": r.reason} for r in refused],
            "not_yet_processed": missing,
        },
        "shards": [
            {
                **shard_stats[s.shard_id]["shard"],
                "file_sha256": shard_stats[s.shard_id]["full_pass"]["file_sha256"],
                "file_bytes": shard_stats[s.shard_id]["full_pass"]["file_bytes"],
                "docs": shard_stats[s.shard_id]["full_pass"]["docs"],
                "exact_dup_rate": shard_stats[s.shard_id]["full_pass"]["exact_dup_rate"],
            }
            for s in processed
        ],
        "full_pass": {
            "total_docs": total_docs,
            "unique_docs": unique_docs,
            "duplicate_docs": global_dups,
            "global_exact_dup_rate": global_dups / total_docs if total_docs else 0.0,
            "intra_shard_dup_docs": intra_dups,
            "cross_shard_dup_docs": global_dups - intra_dups,
            "unique_doc_ratio": unique_docs / total_docs if total_docs else 0.0,
            "total_doc_bytes": total_bytes,
        },
        "sampled": {
            "sampled_docs": sampled_docs,
            "doc_coverage": sampled_docs / total_docs if total_docs else 0.0,
            "quality_buckets": dict(q_buckets),
            "domains": dict(domains),
            "contamination": {
                "docs_checked": contam_checked,
                "docs_with_hits": contam_docs_hit,
            },
        },
        "tokens": {
            "estimated_total_tokens": est_tokens if tokens_known else None,
            "estimate_basis": (
                "per-shard measured bytes/token (Tatva 32k tokenizer) × raw shard "
                "bytes; see each shard's stats for the measured sample"
            ),
        },
    }
    manifest_path = os.path.join(args.out, "MANIFEST.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    _write_composition_md(args.out, manifest, shard_stats, processed)
    print(f"corpus_build_hash: {build_hash}")
    print(f"docs: {total_docs:,} total / {unique_docs:,} unique "
          f"(global exact-dup {global_dups/max(1,total_docs):.2%})")
    print(f"wrote {manifest_path}")
    return 0


def _write_composition_md(out_dir: str, manifest: dict, shard_stats: dict, processed) -> None:
    lines = [
        f"# Corpus composition — {manifest['corpus_id']}",
        "",
        f"Build hash: `{manifest['corpus_build_hash']}`",
        f"Generated: {manifest['generated_utc']} by Tatva Data Factory v{FACTORY_VERSION}",
        "",
        "## Shards (full pass)",
        "",
        "| shard | lang | GB | docs | dup% | LID purity | est tokens | b/tok |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for s in processed:
        st = shard_stats[s.shard_id]
        fp = st["full_pass"]
        tok = st.get("tokens") or {}
        lines.append(
            "| {id} | {lang} | {gb:.1f} | {docs:,} | {dup:.2%} | {pur:.1%} | {tok} | {ratio} |".format(
                id=s.shard_id,
                lang=s.language,
                gb=fp["doc_bytes"] / 1e9,
                docs=fp["docs"],
                dup=fp["exact_dup_rate"],
                pur=st["lid"]["consistency_rate"],
                tok=f"{tok.get('estimated_shard_tokens', 0)/1e9:.2f}B" if tok.get("estimated_shard_tokens") else "—",
                ratio=tok.get("bytes_per_token", "—"),
            )
        )
    g = manifest["full_pass"]
    smp = manifest["sampled"]
    lines += [
        "",
        "## Global (full pass)",
        "",
        f"- documents: {g['total_docs']:,} total, {g['unique_docs']:,} unique "
        f"(unique-doc ratio {g['unique_doc_ratio']:.4f})",
        f"- global exact-duplicate rate: {g['global_exact_dup_rate']:.2%} "
        f"(intra-shard {g['intra_shard_dup_docs']:,}, cross-shard {g['cross_shard_dup_docs']:,})",
        f"- bytes (document text): {g['total_doc_bytes']/1e9:.1f} GB",
        "",
        f"## Sampled analysis (coverage: {smp['doc_coverage']:.2%} of documents)",
        "",
        f"- quality buckets: {smp['quality_buckets']}",
        f"- domains: {smp['domains']}",
        f"- contamination: {smp['contamination']['docs_with_hits']} of "
        f"{smp['contamination']['docs_checked']:,} sampled docs hit the eval set",
        "",
        f"- estimated total tokens (derived, labelled): "
        + (f"{manifest['tokens']['estimated_total_tokens']/1e9:.1f}B"
           if manifest["tokens"]["estimated_total_tokens"] else "not measured"),
        "",
    ]
    with open(os.path.join(out_dir, "COMPOSITION.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="factory", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="check this environment can run the pipeline")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("check", help="validate a shard registry")
    p.add_argument("--registry", required=True)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("run", help="process one shard")
    p.add_argument("--registry", required=True)
    p.add_argument("--shard", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sample-every", type=int, default=DEFAULT_SAMPLE_EVERY)
    p.add_argument("--minhash-every", type=int, default=DEFAULT_MINHASH_EVERY)
    p.add_argument("--token-every", type=int, default=DEFAULT_TOKEN_EVERY)
    p.add_argument("--token-byte-budget", type=int, default=DEFAULT_TOKEN_BYTE_BUDGET)
    p.add_argument("--max-docs", type=int, default=0)
    p.add_argument("--eval-set", default="")
    p.add_argument("--fasttext-model", default="")
    p.add_argument("--tokenizer", default="")
    p.add_argument("--lm", default="", help="char-trigram LM (.lm.gz) for bits/char scoring")
    p.add_argument("--pii-scan", action="store_true", help="count PII occurrences on sampled docs")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("train-lm", help="train a perplexity-proxy LM for one shard")
    p.add_argument("--registry", required=True)
    p.add_argument("--shard", required=True)
    p.add_argument("--lm-dir", required=True)
    p.add_argument("--sample-every", type=int, default=200)
    p.add_argument("--max-mb", type=int, default=20)
    p.set_defaults(fn=cmd_train_lm)

    p = sub.add_parser("build", help="applied-filter build over a measured run")
    p.add_argument("--registry", required=True)
    p.add_argument("--run-dir", required=True, help="output dir of run+merge (the measurement)")
    p.add_argument("--build-out", required=True)
    p.add_argument("--min-quality", type=float, default=0.5)
    p.add_argument("--lm-dir", default="", help="dir of <lang>.lm.gz models; enables ppx filter")
    p.add_argument("--ppx-percentile", type=int, default=99, choices=(50, 90, 99),
                   help="per-language cutoff = this percentile of the measured run")
    p.add_argument("--pii", default="redact", choices=("keep", "redact", "drop"))
    p.add_argument("--eval-set", default="", help="drop contaminated docs when given")
    p.add_argument("--shards", default="", help="comma list to build a subset (partial build)")
    p.add_argument("--emit", default="none", choices=("none", "text"),
                   help="none = hash-only manifest; text = write filtered shards")
    p.add_argument("--neardup-drop", default="",
                   help="neardup-drop.u64 from neardup-merge; enables the near-dup filter")
    p.add_argument("--toxicity", action="store_true",
                   help="drop documents flagged by the toxicity lexicon")
    p.add_argument("--toxicity-lexicon-dir", default="",
                   help="dir of <lang>.txt lexicons merged with the builtin starter")
    p.add_argument("--plugin", action="append", default=[], metavar="NAME",
                   help="enable an installed filter plugin (repeatable); its "
                        "identity enters the filter config sha. See plugins.py")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("report",
                       help="emit a draft EU AI Act Art.53(1)(d) training-content summary")
    p.add_argument("--registry", required=True)
    p.add_argument("--eu-ai-act", action="store_true",
                   help="use the European Commission AI Office template shape")
    p.add_argument("--manifest", default=None,
                   help="BUILD-MANIFEST.json — binds the summary to a reproducible build")
    p.add_argument("--out", default=None, help="write here instead of stdout")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("plugins", help="list installed filter plugins")
    p.set_defaults(fn=cmd_plugins)

    p = sub.add_parser("neardup-sig", help="MinHash-sign every document of one shard")
    p.add_argument("--registry", required=True)
    p.add_argument("--shard", required=True)
    p.add_argument("--sig-dir", required=True)
    p.set_defaults(fn=cmd_neardup_sig)

    p = sub.add_parser("neardup-merge",
                       help="cluster near-dups across all shards, write the drop list")
    p.add_argument("--registry", required=True)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--sig-dir", required=True)
    p.add_argument("--out", required=True, help="path for neardup-drop.u64")
    p.set_defaults(fn=cmd_neardup_merge)

    p = sub.add_parser("extract", help="HTML dir -> blank-line-separated shard text")
    p.add_argument("--in-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--min-chars", type=int, default=80)
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("build-union",
                       help="union disjoint partition builds into one manifest")
    p.add_argument("--build-outs", required=True,
                   help="comma list of partition build dirs")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_build_union)

    p = sub.add_parser("merge", help="merge shard outputs into the build manifest")
    p.add_argument("--registry", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--partial", action="store_true",
                   help="allow merging a subset of shards (coverage is recorded)")
    p.set_defaults(fn=cmd_merge)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
