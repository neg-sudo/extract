# Security

The authoritative threat model lives in [`SECURITY.md`](../SECURITY.md). This
page is the practical summary.

## What is blocked by default

* Parent traversal (`../`), absolute paths, Windows drive letters, UNC paths.
* Windows reserved device names: `CON`, `PRN`, `AUX`, `NUL`, `COM1..9`,
  `LPT1..9` (including with extensions).
* Alternate data streams (`file:stream`).
* Trailing dots and spaces, which Windows silently strips.
* Control characters and Unicode bidi overrides/isolates
  (`U+202A–202E`, `U+2066–2069`, `U+200E`, `U+200F`).
* Symlinks and hardlinks (skipped).
* Devices, FIFOs, and sockets (skipped).
* Duplicate entries, including case-only and Unicode-normalization collisions
  (error unless `--force`).
* Overwriting existing files (error unless `--force`).
* Windows junctions/reparse points in the destination (not followed).
* `setuid`/`setgid`/sticky bits (always stripped).
* Archives exceeding any configured limit.

Unsafe **names** abort the extraction with exit code `3` before anything is
written. Unsafe **entry types** are skipped, or abort with `--strict`.

## Safe writes

Files are opened with `O_EXCL | O_NOFOLLOW` where available. Intermediate
directories are checked with `lstat` and must not be symlinks or junctions.
This closes the classic "write through a pre-created symlink" escape.

If extraction fails, the output directory created by that run is removed. A
pre-existing `-f` destination is never deleted.

## Symlinks

Default: never create symlinks or hardlinks.

```bash
extract --allow-symlinks archive.tar   # only links resolving inside output
extract --strict archive.tar           # fail instead of skipping links
```

A symlink whose target resolves outside the output directory is always a hard
error, even with `--allow-symlinks`.

## Native-only sandbox

```bash
extract --sandbox archive.7z   # exit 6: a helper would be required
extract --sandbox archive.zip  # native extraction, no child process
```

`--sandbox` refuses to execute 7Z/RAR/ZST or any other external helper. ZIP,
TAR, GZIP, BZIP2, and XZ still work using the in-process native extractor. Set
`sandbox = true` in the config file to make this the default.

## External formats

Files from 7Z/RAR/ZST/LZ4 helpers are written only to a private temp directory.
On POSIX helpers run with a file-size rlimit; the full temp tree is validated
against name, link, duplicate, and limit rules before import. The temp directory
is always removed, including on failure. A hostile helper can still fill the
temp filesystem, so use an OS sandbox or disk quota for untrusted external
formats.

## Permission hardening

```bash
extract --no-exec archive.tar          # strip execute bits
extract --preserve-perms archive.tar   # keep safe mode bits (setuid stripped)
```

## What `--insecure` does

`--insecure` permits symlinks (still confined to the output) and disables
permission preservation. It does **not** disable name validation or limits.
It exists for archives that legitimately contain internal links.

## Reporting

Use GitHub private advisories: <https://github.com/neg-sudo/extract/security/advisories/new>.
Do not attach live malware; provide a generator or base64.
