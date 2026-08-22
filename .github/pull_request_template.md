**What this changes**

**Why**

**Checklist**

- [ ] Tests added or updated (`python -m pytest tests/ -q`)
- [ ] `./scripts/demo.sh` still runs; if its hashes changed, that is
      intentional and explained above
- [ ] Anything affecting what a build keeps also enters
      `FilterConfig.canonical()`
- [ ] Deterministic: no wall-clock, unseeded randomness, or ordering
      dependence
- [ ] Docs updated (CLI Reference / User Guide / Troubleshooting)
- [ ] Commits signed off (`git commit -s`) per the DCO in CONTRIBUTING.md
