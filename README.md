# extract

**The secure, intelligent, cross-platform archive utility.**

[![tests](https://github.com/neg-sudo/extract/actions/workflows/test.yml/badge.svg)](https://github.com/neg-sudo/extract/actions/workflows/test.yml)
[![security](https://github.com/neg-sudo/extract/actions/workflows/security.yml/badge.svg)](https://github.com/neg-sudo/extract/actions/workflows/security.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-teal.svg)](LICENSE)

`extract` unpacks archives without letting them unpack you. One command, native
support for the formats that matter, strict path and resource controls,
machine-readable output, and an interactive browser.

```bash
extract backup.zip
extract https://example.com/release.tar.gz
extract --list photos.cbz
extract --search '*.json' project.zip
extract --grep TODO project.zip
extract --tui source.zip
extract --sandbox untrusted.zip
```

## Why this one?

Most extractors compete on format count. `extract` competes on safety,
predictability, and automation:

* **Hostile archives are the default assumption** — traversal, symlink escapes,
  unicode tricks, bombs, and overwrite attacks are handled before anything is
  written.
* **Native core** — ZIP, TAR, TAR.GZ/BZ2/XZ, GZ, BZ2, and XZ need no external
  programs. Uncommon formats use optional helpers, confined to a temp directory.
* **Predictable automation** — stable exit codes and structured `--json`.
* **Intelligence** — magic bytes beat a misleading extension; reports sizes,
  ratio, encryption, and counts.
* **Recursive hygiene** — nested archives have depth, count, size, and ratio
  limits.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/neg-sudo/extract/main/scripts/install.sh | bash
```

Installs to `~/.extract` and links `extract` plus the `x` alias into
`~/.local/bin`. Source downloads are atomic, so a failed request cannot damage
a working installation.

Windows:

```powershell
irm https://raw.githubusercontent.com/neg-sudo/extract/main/install.ps1 | iex
```

Prebuilt binaries for Linux, macOS, and Windows (AMD64 and ARM64) are published
with every tagged release, together with `SHA256SUMS` and optional GPG/Sigstore
signatures. A universal `extract.pyz` is also produced.

```bash
sha256sum -c SHA256SUMS
gpg --verify SHA256SUMS.asc SHA256SUMS
```

From source:

```bash
git clone https://github.com/neg-sudo/extract.git
cd extract
./bin/extract --version
python3 -m unittest discover -s tests -v
```

Python 3.9+ is required for the source install. There are no third-party Python
dependencies.

## Security

| Threat | Default behaviour |
| ------ | ----------------- |
| `../../evil`, absolute paths, drives, UNC | Abort, exit `3`, before writing |
| Symlinks, hardlinks, junctions | Skipped |
| Link escaping the output | Abort |
| Windows reserved names (`CON`, `NUL`, `COM1`...) | Abort |
| Alternate data streams (`file:stream`) | Abort |
| Trailing dots/spaces | Abort |
| Unicode bidi overrides/isolates | Abort |
| Duplicate/case/NFC-colliding entries | Abort |
| Overwriting existing files | Abort unless `--force` |
| Decompression bombs | Abort at limits, checked twice |
| Devices/FIFOs/sockets | Never created |
| `setuid`/`setgid`/sticky bits | Always stripped |
| Executable extraction | `--no-exec` strips exec bits |

Safety is layered:

1. **Validate before writing.** Every member name and type is checked before the
   first byte lands on disk.
2. **Safe writes.** `O_EXCL | O_NOFOLLOW` where available; no directory is
   traversed through a symlink.
3. **Streaming limits.** Bytes are counted while decompressing, so a lying
   header cannot exceed a limit.
4. **Confined external tools.** 7Z/RAR/ZST helpers run in a private temp
   directory under a file-size rlimit; their output is re-validated and imported
   through the safe path. Use `--sandbox` to forbid helpers entirely.

Read the full [threat model](SECURITY.md).

### Limits

```bash
extract untrusted.zip \
  --max-size 10G \
  --max-files 100000 \
  --max-depth 10 \
  --max-ratio 100
```

| Flag | Meaning | Default |
| ---- | ------- | ------- |
| `--max-size` | Total uncompressed bytes | 100 GiB |
| `--max-file-size` | Largest single entry | 50 GiB |
| `--max-files` | Entry count | 1,000,000 |
| `--max-ratio` | Uncompressed ÷ compressed | 1000 (above 64 MiB) |
| `--max-depth` | Nested archive depth | 10 |

Sizes accept `K`, `M`, `G`, `T`, `P`, `iB`, and decimals: `10G`, `1.5GiB`.

## Native formats

No external tools required:

| Format | Examples |
| ------ | -------- |
| ZIP | `.zip .cbz .jar .war .apk .epub .docx .xlsx .pptx .whl .nupkg` |
| TAR | `.tar` |
| TAR + GZIP | `.tar.gz .tgz` |
| TAR + BZIP2 | `.tar.bz2 .tbz2 .tbz` |
| TAR + XZ | `.tar.xz .txz` |
| GZIP / BZIP2 / XZ | `.gz .bz2 .xz` |

Optional helpers for 7Z, RAR, ZST, Brotli, LZ4, LZO, DEB, RPM, CPIO, AR, ISO,
and CAB. `extract` tells you which tool is missing.

## Usage

```bash
extract archive.zip                 # -> ./archive/
extract -C /tmp/out archive.zip     # choose output
extract -f archive.zip              # allow existing dir / overwrite

extract --list archive.zip          # inspect
extract --info archive.zip
extract --check archive.zip         # integrity test
extract --dry-run archive.zip
extract --cat archive.zip file.txt  # write one member to stdout

extract --search '*.json' archive.zip
extract --grep password archive.zip
extract --include 'src/*.py' archive.zip

extract -r bundle.zip --max-depth 3 # recursive
extract --tui archive.zip           # interactive browser
extract --pack src out.tar.gz       # create an archive
```

### Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | Success |
| 1 | Extraction or I/O error |
| 2 | Invalid or corrupted archive |
| 3 | Security violation or limit exceeded |
| 4 | Checksum mismatch |
| 5 | Password required or wrong |
| 6 | Unsupported format |

```bash
extract --check release.zip
case $? in
  0) echo ok ;;
  2) echo corrupted ;;
  3) echo "unsafe archive" ;;
esac
```

### JSON

```bash
extract --json -C out release.zip
```

```json
{
  "archive": "/abs/release.zip",
  "bytes_written": 582193021,
  "directories": 41,
  "duration_ms": 812,
  "exit_code": 0,
  "files": 1842,
  "format": "zip",
  "output": "/abs/out",
  "skipped": 0,
  "status": "success",
  "warnings": []
}
```

### Passwords

```bash
extract -p archive.zip        # prompt
extract -p 'secret' archive.zip
extract --clear-keys
```

Passwords are never printed. The optional keyring stores them at mode `0600`
and is not encrypted at rest.

### TUI

`extract --tui archive.zip` opens a curses browser with search, filtering,
multi-select, and selective extraction. See [docs/tui.md](docs/tui.md).

## Tests and CI

```bash
python3 -m unittest discover -s tests -v
python3 tests/fuzz_smoke.py --iterations 5000
python3 scripts/benchmark.py --size-mb 10 --files 1000
```

The suite covers normal archives, empty and corrupted archives, truncation,
traversal, absolute/drive/UNC paths, reserved names, ADS, unicode bidi, symlinks,
hardlinks, special files, duplicate entries, setuid stripping, every limit,
encryption, checksums, JSON, exit codes, selective extraction, and recursion
depth. CI runs it on Linux, macOS, and Windows across Python 3.9, 3.12, and
3.13, plus lint, Bandit, CodeQL, and scheduled fuzzing.

## Documentation

* [Docs index](docs/index.md)
* [Installation](docs/installation.md)
* [Getting started](docs/getting-started.md)
* [Formats](docs/formats.md)
* [Security](docs/security.md) and [SECURITY.md](SECURITY.md)
* [Limits](docs/limits.md)
* [CLI reference](docs/cli-reference.md)
* [Scripting and CI](docs/scripting.md)
* [Performance](docs/performance.md)

## Contributing

Security and correctness first. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report vulnerabilities through
[private advisories](https://github.com/neg-sudo/extract/security/advisories/new),
not public issues.

## License

MIT. See [LICENSE](LICENSE).
