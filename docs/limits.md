# Limits and decompression bombs

A decompression bomb is a small archive that expands to an enormous amount of
data, a huge number of files, or a deep chain of nested archives. `extract`
enforces five independent limits.

| Flag | Meaning | Default |
| ---- | ------- | ------- |
| `--max-size SIZE` | Total uncompressed bytes | 100 GiB |
| `--max-file-size SIZE` | Largest single entry | 50 GiB |
| `--max-files N` | Number of entries | 1,000,000 |
| `--max-ratio N` | Uncompressed ÷ compressed | 1000 (above 64 MiB) |
| `--max-depth N` | Nested archive depth | 10 |

Sizes accept `K`, `M`, `G`, `T`, `P`, optional `iB`/`B`, and decimals:
`10G`, `512M`, `1.5GiB`, `1024`.

## When limits are checked

1. **Before writing** — from archive metadata (entry count, declared sizes,
   compressed size).
2. **During streaming** — every chunk is counted, so a lying header cannot
   exceed a limit.

If any limit is exceeded, extraction aborts immediately with exit code `3`.
Native formats are validated before the first write, so a rejected archive
leaves no partial tree behind.

## Examples

```bash
extract archive.zip --max-size 2G --max-files 50000
extract untrusted.7z --max-size 500M --max-ratio 50 --max-depth 2
extract -r bundle.tar.gz --max-depth 1
```

## Environment variables

Useful in CI containers where flags are hard to inject:

```bash
EXTRACT_MAX_SIZE=2147483648
EXTRACT_MAX_FILE_SIZE=536870912
EXTRACT_MAX_FILES=50000
EXTRACT_MAX_RATIO=100
EXTRACT_MAX_DEPTH=3
```

Command-line flags take precedence over environment variables, which take
precedence over the config file.

## Choosing values

* For untrusted uploads: `--max-size 1G --max-files 20000 --max-depth 1`.
* For package registries: `--max-size 10G --max-files 200000`.
* For local backups: leave defaults, or raise `--max-size`.

Never raise a limit just to make one archive pass without understanding why it
was rejected.
