# Public-release checklist (Bitbucket → GitHub)

This repo is private. When the decision is made to open the core, work this
list top to bottom. Nothing here is a judgment call — the judgment (whether
and when) lives in `DATA-FACTORY-OSS-PLAN.md` in the ai-adi-llm portfolio.

## Must not ship

| item | why | what to do instead |
|---|---|---|
| `eval-set.jsonl` | our benchmark + honesty-trap prompts; publishing lets any model train on them and destroys the contamination screen's value | ship `build_eval_set.py` (already generic) + a tiny example eval set; document that users generate their own |
| `configs/tatva-sangraha-v1.json` | contains the LLM VM's IP and filesystem paths | ship `configs/example-registry.json` with dummy paths and the same schema |
| `runs/**` manifests | fine to publish *if* we want the receipts public (they are our proof), but they name internal shard paths | either scrub the `path` fields or keep runs/ private and link the published report instead |
| git history | this repo's history is clean (fresh-history extraction), so a normal push is safe — do NOT ever mirror ai-adi-llm | — |

## Already done (2026-08-13)

- Documentation set: Quickstart, User Guide, CLI Reference, Docker,
  Troubleshooting, FAQ — all links verified.
- `examples/` — sample corpus with planted defects, registry, eval set and
  toxicity lexicon; `scripts/demo.sh` runs the whole pipeline in seconds and
  is public-safe (synthetic text, CC0, placeholder "toxic" terms rather than
  slurs).
- Docker image + compose + `Makefile`; `requirements.txt` and
  `environment.yml` for venv and conda.
- `factory.py doctor` for environment diagnosis.
- `.dockerignore` already excludes `eval-set.jsonl`, so the internal
  benchmark material is not baked into images.

## Must add

- **LICENSE** — Apache-2.0 is the proposal; not yet applied because the
  decision is open. `pyproject.toml` currently says `Proprietary`; update it
  in the same commit as the LICENSE file.
- **Trademark posture** — either publish under a neutral engine name with
  "powers Shuddhi" branding, or publish as Shuddhi *with* trademark
  guidelines so no one else can sell "Shuddhi Enterprise".
- **CONTRIBUTING.md + DCO** (or a light CLA) — preserves the ability to
  dual-license enterprise features later.
- **SECURITY.md** — a disclosure address; an OSS repo attracts reports.
- **CI** — the test suite is fast and network-free; a GitHub Actions matrix
  (3.10–3.13) is ~20 lines and is table stakes for external credibility.

## Must decide before the push (not after)

- **The code boundary.** These stay out of the open core by design, because
  they are the commercial edition: hosted receipts registry / audit UI,
  NER-class PII, the toxicity classifier tier, compliance reporting packs,
  multi-node orchestration. Features drift into OSS one PR at a time if the
  boundary is not written down first.
- **Naming.** Slug corrected to `ai-shuddhi-data-factory` on 2026-08-13.
  Decide whether the public repo keeps the product name (with trademark
  guidelines) or ships under a neutral engine name.
- **Maintenance owner.** An unmaintained repo is worse than no repo.

## Sanity gate before pushing public

```bash
grep -rniE "password|api[_-]?key|secret|BEGIN (RSA|OPENSSH|PRIVATE)|AccountKey" .
grep -rn "azureuser\|52\.172\|agentanywhere\|jl_fs\|\.pem" --include="*.py" --include="*.json" --include="*.sh" --include="*.md" .
python3 -m pytest tests/ -q
```

Both greps must come back empty (or only match this checklist) and the suite
must be green.
