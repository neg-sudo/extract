# extract

**The secure, intelligent, cross-platform archive utility.**

`extract` unpacks archives without letting them unpack you. It is a single
command with native support for the formats that matter, strict path and
resource controls, machine-readable output, and an interactive browser.

```bash
extract backup.zip
extract https://example.com/release.tar.gz
extract --list photos.cbz
extract --search '*.json' project.zip
extract --grep TODO project.zip
extract --tui source.zip
```

## Why another extractor?

Most tools optimise for the number of formats. `extract` optimises for:

* **Safety** — path traversal, symlink escapes, unicode tricks, bombs, and
  overwrite attacks are handled by default.
* **Predictability** — stable exit codes and structured JSON for automation.
* **Native coverage** — ZIP, TAR, GZIP, BZIP2, and XZ need no external tools.
* **Intelligence** — content detection beats a misleading file extension.
* **Recursive hygiene** — nested archives have depth, count, and size limits.

## Quick start

```bash
curl -fsSL https://raw.githubusercontent.com/neg-sudo/extract/main/scripts/install.sh | bash
extract --version
extract --check archive.zip
extract archive.zip
```

See [Installation](installation.md) and [Getting started](getting-started.md).

## Security at a glance

| Threat | Default behaviour |
| ------ | ----------------- |
| `../../evil` | Abort with exit code 3 |
| Absolute / drive / UNC paths | Abort |
| Symlinks and hardlinks | Skipped |
| Decompression bomb | Abort at configured limits |
| Windows reserved names / ADS | Abort |
| Unicode bidi filenames | Abort |
| Duplicate entries | Abort |
| setuid/setgid | Stripped |
| Special files | Never created |

Read the full [threat model](../SECURITY.md).

## License

MIT.
