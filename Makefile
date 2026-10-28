PY ?= python3

.PHONY: help test fuzz bench lint compile build install clean

help:
	@echo "make test     run the full unittest suite"
	@echo "make fuzz     run the deterministic fuzz smoke test"
	@echo "make bench    run the native extraction benchmark"
	@echo "make lint     compile and run ruff critical checks"
	@echo "make build    build zipapp + native binary (needs pyinstaller)"
	@echo "make install  install into ~/.extract"
	@echo "make clean    remove build artifacts"

test:
	$(PY) -m unittest discover -s tests -v

fuzz:
	$(PY) tests/fuzz_smoke.py --iterations 5000

bench:
	$(PY) scripts/benchmark.py --size-mb 10 --files 1000

compile:
	$(PY) -m compileall -q lib tests scripts

lint: compile
	ruff check lib tests --select E9,F63,F7,F82 || true

build:
	./scripts/build_binaries.sh

install:
	EXTRACT_INSTALL_DIR="$${EXTRACT_INSTALL_DIR:-$$HOME/.extract}" \
	EXTRACT_BIN_DIR="$${EXTRACT_BIN_DIR:-$$HOME/.local/bin}" \
	./scripts/install.sh

clean:
	rm -rf build dist __pycache__ lib/__pycache__ tests/__pycache__ \
	  scripts/__pycache__ .ruff_cache *.pyz
