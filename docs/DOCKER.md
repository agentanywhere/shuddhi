# Docker

The image exists so nobody has to think about Python versions, virtual
environments, or optional wheels. It contains the engine, every optional
dependency, the test suite, and the example corpus.

## Build

```bash
docker build -t shuddhi .
```

~460 MB, based on `python:3.12-slim`. No GPU, no network access needed at
run time — the pipeline makes no outbound calls.

## The three verbs

```bash
docker run --rm shuddhi doctor    # what this environment can do
docker run --rm shuddhi test      # the full test suite
docker run --rm shuddhi demo      # end-to-end run on the sample corpus
```

Anything else is passed straight to the CLI:

```bash
docker run --rm shuddhi check --registry /work/registry.json
docker run --rm shuddhi --help
```

There is also `shell` for poking around inside (`docker run --rm -it shuddhi shell`).

## Working with your own data

Mount a host directory at `/work`. It is the container's working directory,
so relative paths behave the way you expect:

```bash
docker run --rm -v "$PWD:/work" shuddhi \
    run --registry registry.json --shard news_eng --out run/
```

Everything written under `/work` lands on the host. The container runs as
uid 1000 (`shuddhi`, non-root); on Linux, add `--user "$(id -u):$(id -g)"`
if your host uid differs and you want files owned by you:

```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" shuddhi doctor
```

## docker compose

`docker-compose.yml` mounts `./data` at `/work`:

```bash
mkdir -p data                       # put your corpus + registry here
docker compose run --rm shuddhi demo
docker compose run --rm shuddhi check --registry /work/registry.json
```

## In CI

The provenance gate is designed to be a CI gate — `check` exits non-zero
when any shard is refused:

```yaml
- run: docker build -t shuddhi .
- run: docker run --rm -v "$PWD:/work" shuddhi check --registry /work/registry.json
```

A pull request that adds an untagged or customer-tagged shard then fails the
build, which is the entire point: the rule is enforced by the pipeline, not
by review discipline.

## Notes

- **The language-ID model is not baked in.** `lid.176.ftz` is redistributed
  under its own licence, so fetch it yourself (`make fetch-lid`) and mount it.
  Without it, Shuddhi falls back to Unicode-script identification and says so
  in the stats.
- **Reproducibility holds across the boundary.** The bundled demo produces
  byte-identical hashes on macOS, in a Linux venv, and inside this image.
- **Memory** scales with corpus size in the merge and near-dup stages (they
  hold document hashes and MinHash signatures). Roughly 40 bytes per document:
  a 33-million-document corpus merges comfortably inside 2 GB. Raise Docker
  Desktop's memory limit if you are working at that scale.
