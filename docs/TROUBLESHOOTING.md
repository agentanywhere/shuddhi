# Troubleshooting

**Run `python3 factory.py doctor` first.** Most problems are environment
problems, and it names them in one line.

---

### `ModuleNotFoundError: No module named 'numpy'`

You are running a different Python than the one you installed into. This is
the single most common failure — many machines have three or four `python3`
binaries.

```bash
which -a python3          # how many do you have?
python3 factory.py doctor # doctor prints sys.executable
```

Fix by installing into *that* interpreter, or activate the environment:

```bash
source .venv/bin/activate      # venv
conda activate shuddhi         # conda
python3 -m pip install -r requirements.txt
```

Or sidestep it entirely: `docker run --rm shuddhi doctor`.

---

### `ModuleNotFoundError: No module named 'builder'` (or another module) in Docker

The image is missing a source file. Check your `.dockerignore` for
unanchored patterns — `build*/` also matches `builder.py` and silently drops
it from the image. Use anchored patterns (`/build`), then confirm:

```bash
docker run --rm --entrypoint sh shuddhi -c "ls /app/*.py"
```

---

### `check` exits 2 and refuses a shard

Working as designed. Read the reason:

- *"data_class 'customer' is never trainable"* — the exclusion is absolute
  and has no override. Remove the shard from the registry.
- *"untagged shard: missing provenance field(s)"* — fill in every field.
- *"unknown data_class"* — must be `public`, `licensed`, or `synthetic-own`.
- *"suspect provenance"* — the name looks like customer material. If it
  genuinely is not, add `"reviewed_by": "<name> (<date>, <what you checked>)"`.

---

### The perplexity filter drops nothing

Almost always the ordering. `build` reads the cutoff from the *measurement*,
so the models must exist before you measure:

```bash
factory.py train-lm --registry R --shard S --lm-dir lms/    # 1
factory.py run --registry R --shard S --out run/ --lm lms/<lang>.lm.gz   # 2
factory.py merge --registry R --out run/                    # 3
factory.py build --registry R --run-dir run/ --lm-dir lms/ ...  # 4
```

`build` warns on stderr when `--lm-dir` is given but the run has no
perplexity statistics. Also note that percentile cutoffs need scale — on a
few dozen documents, p99 sits at the worst document.

---

### The demo dropped a normal-looking document

Expected on a tiny corpus, and worth understanding. `--ppx-percentile 99`
against an 11-document shard puts the cutoff at essentially the worst
document, so one ordinary document falls outside it. Percentile filters are
meaningful at corpus scale, not on demo fixtures.

---

### `RuntimeError: ... is not in the measured run's hash set`

A shard file changed after you measured it. The build refuses rather than
silently producing something unmeasured. Re-run `run` and `merge` for that
shard, then build again.

---

### `partition manifests disagree on filter_config_sha256`

The partitions were built with different settings, or with different engine
versions. Rebuild all partitions with identical flags. Note that per-language
perplexity cutoffs are computed across the whole corpus precisely so that
partition configs match.

---

### Everything is classified `und` / language purity looks wrong

You are on the Unicode-script fallback because `lid.176.ftz` is absent.
Script identification cannot separate languages sharing a script. Fetch the
model:

```bash
make fetch-lid
factory.py run ... --fasttext-model lid.176.ftz
```

`"method": "script"` in the stats confirms which path ran.

---

### Near-dup merge is slow or memory hungry

It holds MinHash signatures for every document (32 × 8 bytes each, ~256 bytes
per document — roughly 8 GB at 33 million documents, memory-mapped from
disk). Signatures stream from `--sig-dir`, so give that directory room, and
prefer running `neardup-sig` per shard in parallel and `neardup-merge` once.

---

### The build is slower than expected

Per-document cost is dominated by whichever filters are enabled: perplexity
scoring and contamination screening are the expensive ones. Measure on one
shard with `--max-docs` before committing to a full corpus, and partition
across cores (see [scaling out](USER-GUIDE.md#8-scaling-out)).

---

### Docker output files are owned by the wrong user

The container runs as uid 1000. On Linux, match your own uid:

```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" shuddhi ...
```

---

### Still stuck

`run/<shard>.stats.json` and `build/BUILD-MANIFEST.json` record the engine
version, Python version, library versions, and every threshold used. Include
them in any bug report.
