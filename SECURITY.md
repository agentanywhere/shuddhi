# Security Policy

## Reporting a vulnerability

Please report privately to **security@shephertz.com** rather than opening a
public issue. Include what you found, how to reproduce it, and what an
attacker could do with it. We will acknowledge within five working days and
keep you updated until it is resolved. If you would like credit in the
release notes, say so.

## What counts as a vulnerability here

Beyond the usual (code execution, path traversal, dependency issues), this
project has two classes of bug that are security-relevant because of what
its output is used for:

**Receipt integrity.** Anything that lets two materially different corpora
produce the same `filtered_build_hash`, or lets a build's contents change
without its config sha changing. That defeats the tool's entire purpose.
Practical detection is genuinely hard, so these reports are especially
welcome.

**Provenance gate bypass.** Any input that gets a `customer`,
`customer-derived`, or `evaluation-only` shard admitted into a build. The
refusal is meant to be absolute and unconditional.

Also in scope: PII redaction that leaves the original value recoverable in
emitted text, and contamination screening that misses a verbatim eval item.

## What is out of scope

- The pipeline trusts its input corpora. Feeding it a hostile 500 GB file
  and observing resource exhaustion is expected behaviour, not a finding.
- Registries are configuration and are trusted: a registry that points at
  `/etc/shadow` will read `/etc/shadow` with your permissions.
- Filter plugins execute as installed code, by design. Installing a hostile
  plugin is equivalent to installing hostile software.
- Quality, toxicity, and PII filters are heuristics with documented limits.
  Finding text they miss is a tuning issue, not a vulnerability, unless the
  miss is systematic and trivially exploitable.

## Supported versions

The latest release on the default branch. This is a young project; we do not
yet backport fixes.
