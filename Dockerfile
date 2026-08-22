# Shuddhi (शुद्धि) — Data Factory
#
# A self-contained image: no Python setup, no dependency hunting, no
# "which python3 has numpy" surprises.
#
#   docker build -t shuddhi .
#   docker run --rm shuddhi doctor                 # verify the environment
#   docker run --rm shuddhi demo                   # full pipeline on the sample corpus
#   docker run --rm -v "$PWD:/work" shuddhi check --registry /work/registry.json
#
# Your data stays yours: mount a host directory at /work and every path you
# pass is read from and written to that mount. The image never phones home,
# and the pipeline makes no network calls.
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Shuddhi Data Factory" \
      org.opencontainers.image.description="Receipts-first dataset cleansing engine for sovereign AI" \
      org.opencontainers.image.source="https://github.com/agentanywhere/shuddhi"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencies first, in their own layer, so code edits do not re-resolve them.
# numpy is required; the rest are the optional extras, included here because an
# image exists precisely so nobody has to think about extras.
RUN pip install --no-cache-dir \
        "numpy>=1.24" \
        tokenizers \
        trafilatura \
        fasttext-predict \
        pytest

WORKDIR /app
COPY . /app

# Non-root by default. /work is the mount point for your corpora and outputs.
RUN useradd --create-home --uid 1000 shuddhi \
 && mkdir -p /work \
 && chown -R shuddhi:shuddhi /work /app \
 && chmod +x /app/scripts/*.sh
USER shuddhi
WORKDIR /work

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["doctor"]
