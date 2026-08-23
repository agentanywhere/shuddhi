# Contributing to Shuddhi

Thanks for considering it. This project has an unusual constraint that
shapes everything below: **Shuddhi's output is a receipt other people rely
on.** A change that alters what a build keeps, without altering the build's
identity, breaks the guarantee the whole tool exists to provide. So the
review bar is about correctness and honesty more than style.

## Ground rules

1. **Every measurement carries its coverage.** Full-pass, sampled, and
   derived numbers are labelled and never mixed silently. This applies to
   code, output, and documentation.
2. **Anything that changes verdicts changes the config sha.** New filter?
   New threshold? New scorer probe size? It goes into
   `FilterConfig.canonical()`. There is a test for this; add yours.
3. **Determinism is not negotiable.** No wall-clock, no `random` without a
   fixed seed, no dict-iteration-order dependence, no reliance on shard
   order. The same inputs must produce the same hashes on any machine.
4. **The provenance gate has no override.** Patches adding a flag,
   environment variable, or config field that admits `customer`-class data
   will be declined regardless of how convenient the use case is.
5. **Say what the code does not do.** Honest limits belong in docstrings and
   docs. We would rather ship a documented limitation than an implied
   capability.

## Getting set up

```bash
git clone <repo> && cd shuddhi
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
shuddhi doctor      # confirms the environment
python3 -m pytest tests/ -q    # 111 tests, seconds, no network
./scripts/demo.sh              # end-to-end on the sample corpus
```

## Making a change

- **Tests are required**, with tiny fixtures and no network. Look at
  `tests/test_registry.py` for the style: each test states the rule it
  protects.
- **Run the demo before and after.** If your change alters the demo's hashes,
  that is either the point of your patch or a bug — say which in the PR.
- **Keep the CLI stable.** Flags appear in other people's scripts and in
  build manifests.
- **Documentation is part of the change.** New flag → CLI Reference. New
  behaviour → User Guide. New failure mode → Troubleshooting.

## Adding a filter

Most new filters should be **plugins**, not core changes — see
[docs/EXTENDING.md](docs/EXTENDING.md) and `examples/plugin/`. A filter
belongs in core only if it is general across corpora and languages, has no
heavy dependencies, and is cheap enough to run on every document.

## Developer Certificate of Origin

Contributions are accepted under the [DCO](https://developercertificate.org/):
you certify that you wrote the patch or have the right to submit it under
this project's licence. Sign off each commit:

```bash
git commit -s -m "your message"
```

which appends `Signed-off-by: Your Name <your@email>`. No CLA, no copyright
assignment.

## Reporting bugs

Include `run/<shard>.stats.json` and `build/BUILD-MANIFEST.json` if you have
them — they record the engine version, Python version, library versions, and
every threshold used, which usually identifies the problem immediately. Also
include `shuddhi doctor` output.

For anything security-sensitive, see [SECURITY.md](SECURITY.md) instead of
opening an issue.

## What we are less likely to merge

- Throughput work that trades away determinism.
- Filters that need a GPU or a network call at build time.
- Vendored dependencies.
- Anything that makes a manifest claim more than was measured.
