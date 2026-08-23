# Shuddhi — common tasks. `make help` lists everything.
PYTHON ?= python3
VENV   ?= .venv
IMAGE  ?= shuddhi:latest

.DEFAULT_GOAL := help
.PHONY: help doctor venv conda test compat demo docker docker-demo fetch-lid clean

help:  ## show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk -F':.*?## ' '{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

doctor:  ## check whether the current interpreter can run the pipeline
	@$(PYTHON) -m shuddhi doctor

venv:  ## create a virtualenv in ./.venv and install everything
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --upgrade pip
	$(VENV)/bin/pip install --quiet -r requirements.txt
	@echo
	@$(VENV)/bin/python -m shuddhi doctor
	@echo "\nActivate it with:  source $(VENV)/bin/activate"

conda:  ## create the 'shuddhi' conda environment
	conda env create -f environment.yml || conda env update -f environment.yml
	@echo "\nActivate it with:  conda activate shuddhi"

compat:  ## run the suite on the OLDEST supported Python (3.10) via Docker
	@# Developing on 3.12 hides syntax that 3.10 rejects — a nested f-string
	@# shipped once and only CI caught it. This is the same check, locally.
	docker run --rm -v "$(PWD):/src" -w /src python:3.10-slim sh -c \
	  "pip install -q -r requirements.txt && pip install -q -e . && \
	   python -m pytest tests/ -q --ignore=tests/test_ui_playwright.py"

test:  ## run the test suite
	$(PYTHON) -m pytest tests/ -q

demo:  ## run the full pipeline on the bundled example corpus
	PYTHON=$(PYTHON) ./scripts/demo.sh

docker:  ## build the container image
	docker build -t $(IMAGE) .

docker-demo: docker  ## run the demo inside the container
	docker run --rm $(IMAGE) demo

fetch-lid:  ## download the fastText lid.176 language-ID model (~1 MB)
	curl -fL -o lid.176.ftz https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz
	@echo "Downloaded lid.176.ftz — pass it with --fasttext-model lid.176.ftz"

clean:  ## remove generated artefacts (never touches your corpora)
	rm -rf demo-out out build sigs lms .pytest_cache **/__pycache__ __pycache__ *.egg-info
