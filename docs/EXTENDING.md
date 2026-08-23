# Extending Shuddhi

The built-in filters cover corpus hygiene: duplicates, junk, gibberish,
obvious toxicity, benchmark contamination, pattern-level PII. Everything
past that is somebody's specialised problem — clinical PHI, financial
document policy, a house style rule, a classifier you trained — and
specialised problems do not belong inside a general engine.

So Shuddhi has a seam. Any installed Python package can contribute a filter
that a build applies as though it were built in, **without forking**.

## The contract

Four members:

```python
class MyFilter:
    name = "acme-medical-phi"     # matches the entry-point key
    version = "1.4.0"

    def identity(self) -> dict:
        """Everything that changes this filter's verdicts."""
        return {"rulepack_sha256": self._sha, "strictness": self.strictness}

    def check(self, text: str) -> str | None:
        """A short drop reason, or None to keep."""
        return "PHI detected" if self._scan(text) else None
```

Register it in your package's `pyproject.toml`:

```toml
[project.entry-points."shuddhi.filters"]
acme-medical-phi = "acme_shuddhi:PhiFilter"
```

Then:

```bash
pip install acme-shuddhi
shuddhi plugins                        # confirm it is visible
shuddhi build ... --plugin acme-medical-phi
```

A complete, installable example is in [`examples/plugin/`](../examples/plugin/).

## `identity()` is the load-bearing part

Whatever it returns is folded into the build's `filter_config_sha256`, which
is recorded in the build manifest beside the hashes.

To be precise about what that does and does not do: `filter_config_sha256`
records *how* the corpus was selected. `filtered_build_hash` is computed over
the selected documents themselves and does not include the config — so if
your filter changes its verdicts, the document set changes and the hash moves
with it. What the config sha adds is the ability to tell two builds apart
that selected the same documents by different means.

**A plugin that changes its verdicts without changing its identity breaks the
receipt** — it would let two materially different corpora claim the same
hash, which is the one thing this system exists to prevent. So include
everything a reviewer would need to reproduce your decisions: model file
shas, rule-pack versions, thresholds, the lot. Do not include timestamps,
hostnames, or anything else that varies between runs without changing
behaviour — that makes hashes unreproducible, which is the opposite failure.

The test suite asserts this both ways: adding a plugin changes the config
sha, and changing a plugin's configuration changes it again.

## Rules the engine enforces

- **Opt-in only.** Installing a package never silently changes a build. You
  name it with `--plugin`, and naming it puts it in the hash.
- **Missing means failure.** If you ask for a plugin that is not installed,
  the build stops. Silently skipping a filter would produce a manifest that
  misrepresents itself.
- **The contract is checked at load.** Missing members, or an entry-point key
  that disagrees with the plugin's `name`, is an error — the name is what
  appears in the manifest, so it has to be true.
- **Separate accounting.** Plugin drops are counted under `plugin:<name>`, so
  a manifest always shows which filter removed what.

## Where plugins run

```
exact-dup → near-dup → quality → perplexity → toxicity → contamination
          → plugins (in the order you name them) → PII policy
```

Plugins see documents that survived every built-in filter, which keeps
expensive custom logic off the obvious junk.

## Performance

`check()` is called once per surviving document — tens of millions of times
on a real corpus. Precompute in `__init__`, prefer set lookups to regex
alternation where you can (the built-in toxicity filter moved from ~1–2 ms
to ~250 µs per document exactly that way), and bound any work you do on very
long documents by scanning a prefix rather than the whole text.

## Testing your plugin

```python
def test_identity_covers_behaviour():
    a = FilterConfig(plugin_identities=identities([MyFilter(strictness=1)]))
    b = FilterConfig(plugin_identities=identities([MyFilter(strictness=9)]))
    assert a.sha256() != b.sha256()
```

If that assertion can fail, your plugin can silently change a corpus while
its receipt claims otherwise. It is the first test to write.
