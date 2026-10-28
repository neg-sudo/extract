# Security policy

`extract` is designed to unpack hostile archives. Security is the primary
design constraint, not an afterthought. This document describes the threat
model, the guarantees, and how to report problems.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 3.x     | yes       |
| 2.x     | security fixes only |
| < 2.0   | no        |

## Reporting a vulnerability

Please **do not open a public issue** for a vulnerability that can escape the
output directory, bypass a limit, or write arbitrary files.

Use GitHub's private advisory flow:

<https://github.com/neg-sudo/extract/security/advisories/new>

Include:

* the `extract --version` output and platform;
* a minimal archive (base64 or a generator script) if it is not live malware;
* the command line, exit code, and `--json` output;
* the impact you believe is possible.

You will receive an acknowledgement within 72 hours. Please give us a
reasonable window to ship a fix before public disclosure.

## Threat model

We assume the **archive is attacker-controlled**. We assume the filesystem,
destination directory, and the `extract` binary itself are trusted. We do not
assume that external helper programs (`7z`, `unrar`, ...) are safe against
malicious input; for this reason external extractors run in a private temporary
directory and their output is re-validated before it is imported.

### In scope

* Path traversal (Zip Slip), absolute paths, Windows drive and UNC paths.
* Symlink and hardlink attacks, including links that resolve outside the
  destination, and pre-existing symlinks in the destination.
* Decompression bombs: total bytes, per-file bytes, entry count, compression
  ratio, and nested-archive recursion depth.
* Windows-specific abuse: reserved device names (`CON`, `NUL`, `COM1`...),
  alternate data streams (`file:stream`), trailing dots and spaces.
* Unicode bidirectional override and isolate characters that disguise an
  extension or path.
* Archive-overwrite and duplicate-entry attacks.
* Special files (devices, FIFOs, sockets).
* Malicious permission bits (setuid, setgid, sticky).
* Executable extraction (`--no-exec`).
* Corrupted and truncated archives producing crashes instead of clean errors.
* External-tool output that is not confined to a temp directory.

### Out of scope

* Attacks that require the attacker to already control the destination
  directory or the user's account.
* Kernel or filesystem bugs.
* Side channels (timing, power).
* Password strength of archives you choose to open.
* Malware that is safely written to disk as an ordinary, non-executable file.

## Guarantees

For **native formats** (ZIP, TAR, GZIP, BZIP2, XZ) the following hold:

1. Every member name is validated before anything is written. Unsafe names
   abort the extraction with exit code `3`.
2. Writes use `O_EXCL | O_NOFOLLOW` where the platform supports it, and no
   intermediate directory is traversed through a symlink or Windows junction.
3. Symlinks and hardlinks are skipped by default. `--allow-symlinks` permits
   them only when the resolved target stays inside the output directory.
   `--strict` turns skipping into a hard failure.
4. Files are streamed while counting bytes; the per-file and total limits are
   enforced during extraction, not only from untrusted headers.
5. Duplicate entries are rejected unless `--force` is given.
6. Special files are never created.
7. `setuid`, `setgid`, and sticky bits are always stripped.
8. Limits are applied to the **uncompressed** size and entry count before the
   first write, based on archive metadata, and again while streaming.
9. Names that collide after Unicode NFC normalization or casefolding are
   rejected, preventing overwrite on Windows and default macOS filesystems.
10. If extraction fails, a directory created by this run is removed instead of
    leaving a partial tree.

External formats (7Z, RAR, ZST, LZ4, ...) are unpacked into a private temporary
directory. On POSIX the helper runs with `RLIMIT_FSIZE` (and no core dumps) so
it cannot emit an oversized file. The entire resulting tree is then validated
before import—names, link targets, duplicates, and all limits—and copied with
the same safe write primitives. A malicious external tool cannot write directly
into your destination. Resource exhaustion inside the helper's temp directory
remains possible; run untrusted external formats under an OS sandbox or disk
quota when that matters.

## Limits

| Limit | Option | Default |
| ----- | ------ | ------- |
| Total uncompressed bytes | `--max-size` | 100 GiB |
| Single entry bytes | `--max-file-size` | 50 GiB |
| Entry count | `--max-files` | 1,000,000 |
| Compression ratio | `--max-ratio` | 1000:1 (enforced above 64 MiB) |
| Nested recursion depth | `--max-depth` | 10 |

`--insecure` only affects symlink handling and permission preservation; it does
**not** disable name validation. Prefer raising a limit over disabling
protection.

## Password handling

Passwords are read with `getpass` when omitted, are never printed, and are
passed to helper tools through argument lists (not a shell). If you opt in with
the keyring, the password is stored in
`~/.local/share/extract/keys/<sha256-of-path>` with mode `0600`; it is not
encrypted at rest. Use `extract --clear-keys` to remove stored passwords.

## Fuzzing and tests

* `tests/` contains unit and integration tests for traversal, bombs, unicode,
  symlinks, corruption, encryption, and exit codes.
* `tests/fuzz_smoke.py` is a deterministic parser fuzzer used in CI.
* `fuzz/` contains optional Atheris targets for continuous fuzzing.
* CI runs the test suite on Linux, macOS, and Windows across supported Python
  versions.

## Verifying a release

Every release publishes `SHA256SUMS`, an optional GPG detached signature
(`SHA256SUMS.asc`), and an optional Sigstore bundle. Verify before running a
downloaded binary:

```bash
sha256sum -c SHA256SUMS
gpg --verify SHA256SUMS.asc SHA256SUMS
```

Never install a binary from a mirror.
