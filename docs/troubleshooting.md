# Troubleshooting

## "security violation" / exit code 3

The archive contains a member that cannot be written safely. Extract with
`--list` to inspect names. Common causes:

* `../` or absolute paths (Zip Slip).
* Windows device names or ADS (`CON`, `file:stream`).
* Unicode bidi control characters.
* A configured limit was exceeded.

`--insecure` only relaxes internal symlinks and permissions; it does not allow
traversal. Do not disable name validation.

## "output directory exists" / exit code 1

Use `-f/--force`, or choose another `-C` directory. `extract` refuses to merge
into an existing directory by default to avoid overwrite attacks.

## Password required / exit code 5

```bash
extract -p archive.zip          # prompt
extract -p 'secret' archive.zip
```

For CI, prefer a secret manager or stdin prompt over a literal flag in shell
history. `extract --clear-keys` removes cached passwords.

## Unsupported format / exit code 6

Native support covers ZIP, TAR, GZ, BZ2, and XZ. Install the helper for other
formats:

```bash
# Debian/Ubuntu
sudo apt install p7zip-full unrar-free zstd

# macOS
brew install p7zip zstd
```

`extract` prints a hint when a helper is missing.

## Corrupted archive / exit code 2

Check with `extract --check`. If it fails, the download or the archive itself is
bad. Native extractors catch truncation and bad CRCs and return code 2.

## RAR extraction fails

RAR is proprietary. Try `unrar`, `unar`, `7z`, or `bsdtar`, in that order.
`unrar-free` does not support all RAR5 features.

## A nested archive was skipped

Recursion respects `--max-depth` (default 10) and never follows symlinks. If a
self-referencing archive is detected, raise `--max-depth` only if you trust the
source.

## TUI does not start

The TUI needs an interactive terminal and a native zip/tar archive. Pipes,
redirects, and non-native formats fall back to listing. Use `--list --json` in
scripts.

## Progress output looks garbled

The spinner is disabled automatically when stdout is not a TTY. Use `-q` or
`--json` in logs.

## Verifying a release

```bash
sha256sum -c SHA256SUMS
gpg --verify SHA256SUMS.asc SHA256SUMS
```

See `SECURITY.md`.
