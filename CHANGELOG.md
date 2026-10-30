# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-10-27

### Added

- Native extraction for ZIP, TAR (plain/gz/bz2/xz), GZIP, BZIP2, and XZ using
  only the Python standard library. These formats no longer require external
  programs.
- Decompression-bomb protection with configurable limits: `--max-size`,
  `--max-file-size`, `--max-files`, `--max-ratio`, `--max-depth`. Limits are
  checked against metadata before writing and enforced again while streaming.
- Path sanitization for traversal, absolute paths, Windows drives and UNC
  paths, reserved device names, alternate data streams, trailing dots/spaces,
  control characters, and Unicode bidi overrides/isolates.
- Symlink and hardlink protection. Links are skipped by default; `--allow-symlinks`
  permits only links that resolve inside the destination; `--strict` fails hard.
- Safe writes using `O_EXCL | O_NOFOLLOW`, with no traversal through existing
  symlinks or Windows junctions, plus duplicate-entry and overwrite protection.
- Collision detection uses NFC normalization and casefolding, blocking archives
  that overwrite each other on case-insensitive or normalizing filesystems.
- Failed extractions remove the output directory they created, so no partial
  tree is left behind.
- Special-file (device/FIFO/socket) blocking and `setuid`/`setgid` stripping.
  `--no-exec` strips execute bits; `--preserve-perms` keeps safe bits.
- External formats (7Z, RAR, ZST, LZ4, ...) are unpacked into a private temp
  directory under an `RLIMIT_FSIZE` cap on POSIX, then fully pre-validated and
  imported through the same safe write path and limits.
- Stable exit codes: `0` success, `1` extraction error, `2` invalid archive,
  `3` security violation, `4` checksum mismatch, `5` password required,
  `6` unsupported format. `--check` is an alias for `--test`.
- Predictable `--json` result objects with `status`, `archive`, `format`,
  `files`, `bytes_written`, `duration_ms`, `output`, `warnings`, and `exit_code`.
- Archive search: `--search GLOB` (names) and `--grep PATTERN` (text contents).
- Selective extraction with `-I/--include GLOB`.
- Real interactive TUI (`--tui`): search, filter, multi-select, and selective
  extraction via a curses browser for zip/tar archives.
- Native packing for `.zip`, `.tar`, `.tar.gz`, `.tar.bz2`, `.tar.xz`, and `.gz`.
- Archive intelligence: magic-byte detection overrides misleading extensions
  and reports confidence, counts, compressed/uncompressed sizes, ratio, and
  encryption state.
- Optional `--delete-nested` and `--on-error stop|continue` for recursive mode.
- `--sandbox` native-only mode: refuses to execute any external helper.
- Safe URL handling: downloaded filenames are sanitized, downloads stream to a
  temp directory, and `--max-size` also caps the download.
- 76-test suite covering normal archives, every malicious class above,
  corruption, encryption, limits, JSON, exit codes, selective extraction,
  case/NFC collisions, partial-output cleanup, download naming, and HTTP URLs.
- GitHub Actions: tests on Linux/macOS/Windows and Python 3.9/3.12/3.13, lint,
  Bandit + CodeQL, scheduled fuzzing, and multi-architecture binary releases
  with `SHA256SUMS`, optional GPG and Sigstore signatures.
- Documentation site scaffolding under `docs/`, `SECURITY.md`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, issue and PR templates, and Dependabot.

### Changed

- The project is repositioned as **the secure, intelligent, cross-platform
  archive utility**. Security and predictability now take priority over format
  count.
- Unsafe member names now abort the extraction instead of being silently
  skipped. Symlinks remain skip-by-default unless `--strict` is used.
- `--insecure` only relaxes symlink and permission handling; it no longer
  disables name validation.

### Fixed

- Windows/legacy consoles no longer crash when printing status symbols; output
  is reconfigured to UTF-8 with replacement on unsupported code pages.
- `Colors.disable()` no longer replaces itself with a string.
- Flattening no longer moves symlinks in a way that could change their target.
- Truncated/corrupted archives now exit with code `2` instead of a traceback or
  a misleading success.
- `--diff` works without positional archive arguments and supports native
  zip/tar member comparison.
- `--parallel` no longer crashes on an internal attribute name.

## [2.0.0] - 2026-10-27

### Fixed

- Installer repository URLs now point to `neg-sudo/extract` instead of a
  non-existent owner.
- Downloads are atomic (`mktemp` then `mv`), so a failed download cannot
  truncate an existing installation.
- The launcher resolves symlinks portably (no `readlink -f`) so `x` works on
  macOS and through `~/.local/bin`.

### Added

- Universal extractor covering 50+ formats, magic-byte detection, zip-slip
  protection, smart flattening, junk removal, list/info/test/dry-run, `--cat`,
  JSON output, history, keyring, notifications, clipboard copy, `--open`, URL
  download, parallel extraction, recursion, watch mode, packing, checksums,
  configuration, plugins, completions, and a TUI entry point.

## [1.0.0]

- Initial release.
