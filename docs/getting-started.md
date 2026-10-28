# Getting started

## Extract

```bash
extract archive.zip          # -> ./archive/
extract archive.tar.gz       # -> ./archive/
extract -C /tmp/out archive.zip
```

Output directory rules:

1. `-C`/`-d` wins.
2. `default_dir` from the config is used if set.
3. Otherwise the archive name without its extension, next to the archive.

`-f/--force` allows writing into an existing output directory and overwriting
existing files. Without it, an existing directory is an error (exit code 1).

## Inspect before extracting

```bash
extract --list archive.zip
extract --info archive.zip
extract --check archive.zip
extract --search '*.json' archive.zip
extract --grep password archive.zip
extract --cat archive.zip path/to/file.txt
extract --dry-run archive.zip
```

`--json` works with all of the above:

```bash
extract --json --info archive.zip | jq .uncompressed_bytes
```

## Select files

```bash
extract -I 'src/*.py' archive.zip
extract -I 'docs/' -I 'README.md' archive.zip
```

Only matching members are extracted; limits still apply to the whole archive
metadata.

## Recursive extraction

```bash
extract -r bundle.zip --max-depth 3
```

Nested archives are extracted beneath the parent output. Depth, file count, and
size limits apply. Use `--delete-nested` to remove nested archives after a
successful extraction, and `--on-error stop` to halt on the first failure.

## Remote archives

```bash
extract https://example.com/file.tar.gz
extract --list https://example.com/file.zip
```

The archive is downloaded to a temporary directory, processed, and removed.
For full selective remote extraction, download once and use `--include`.

## Interactive browser

```bash
extract --tui archive.zip
```

Search, select, and extract only what you need. See [TUI](tui.md).

## Next steps

* [Security and threat model](../SECURITY.md)
* [Limits](limits.md)
* [CLI reference](cli-reference.md)
* [Scripting and CI](scripting.md)
