# Development

## Layout

```
lib/
  extract.py      CLI, detection, orchestration, TUI, packing
  safeops.py      security core and native extractors
bin/
  extract         portable launcher
scripts/
  install.sh      Unix installer
  benchmark.py    performance harness
  build_binaries.sh / .ps1
tests/
  test_formats.py
  test_security.py
  test_cli.py
  fuzz_smoke.py
fuzz/
  fuzz_paths.py   Atheris target for name sanitization
  fuzz_zip.py     Atheris target for ZIP parsing
docs/
```

## Rules

1. All path construction goes through `safeops.sanitize_member_name`,
   `prepare_path`, and `open_write`.
2. Limits are checked twice: metadata and streaming.
3. External tools run in a private temp directory; output is imported through
   the safe path.
4. New formats require a malicious-archive test.
5. Python 3.9 compatibility: no `match`, no `X | Y` type unions, no
   `tomllib` dependency.

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 tests/fuzz_smoke.py --iterations 5000
python3 -m compileall -q lib tests
ruff check lib tests --select E9,F63,F7,F82
bandit -q -ll -r lib
```

## Building

Universal zipapp:

```bash
python3 -m zipapp lib -m "extract:main" -p "/usr/bin/env python3" -o extract.pyz
./extract.pyz --version
```

Standalone binaries (requires PyInstaller):

```bash
./scripts/build_binaries.sh
```

Release workflow builds Linux, macOS, and Windows binaries for AMD64 and ARM64,
then publishes `SHA256SUMS` with optional GPG and Sigstore signatures.

## Adding a native format

1. Add detection in `Extractor.detect_by_magic`/`_detect_by_extension`.
2. Implement a bounded reader in `safeops.py` that validates all names before
   writing and streams through `_copy_limited`.
3. Route it in `Extractor._native_kind`.
4. Add normal, malicious, corrupted, and limit tests.
5. Document it in `docs/formats.md`.

## Releasing

1. Update `VERSION` in `lib/extract.py`, `pyproject.toml`, and the installers.
2. Update `CHANGELOG.md`.
3. Tag: `git tag -s v3.0.0 -m "v3.0.0"` and push the tag.
4. Verify the release assets and signatures.
