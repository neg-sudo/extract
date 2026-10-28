# Contributing

Thanks for helping. `extract` is a security tool first, so correctness and
safety take priority over feature count.

## Development setup

```bash
git clone https://github.com/neg-sudo/extract.git
cd extract
python3 -m unittest discover -s tests -v
./bin/extract --version
```

There are no required third-party Python dependencies. Optional tools
(`7z`, `unrar`, `zstd`, ...) are only used for uncommon formats and are skipped
by the test suite when missing.

## Ground rules

* A new archive format must have extraction tests, including a malicious
  variation.
* Any code that builds a filesystem path must go through `lib/safeops.py`.
* Never pass untrusted names directly to `tar`, `unzip`, or `7z` in a way that
  writes into the destination. Use the temp-dir-and-validate pattern.
* Do not add a mandatory runtime dependency without discussion.
* Keep the tool usable without a network connection.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 tests/fuzz_smoke.py --iterations 5000
python3 -m compileall -q lib tests
ruff check lib tests --select E9,F63,F7,F82
```

CI runs the suite on Ubuntu, macOS, and Windows. Windows-specific tests that
need symlink privileges are skipped automatically.

## Pull requests

* Keep changes focused and describe the security impact.
* Update `README.md` and `docs/` for new flags or behaviour.
* Add an entry to `CHANGELOG.md`.
* Do not commit secrets, keys, or real malware samples. Use generators.

## Commit messages

Use imperative mood, for example:

```
Add --max-ratio enforcement during streaming
Fix symlink flattening escape
```

## Code style

* Python 3.9+ (the code must run on 3.9; avoid 3.10-only syntax).
* Standard library only for core functionality.
* No comments unless they explain **why**, not what.
* Prefer explicit errors (`safeops.ExtractError` subclasses) over booleans.

## Security reports

Do not open a public issue. See [SECURITY.md](SECURITY.md).
