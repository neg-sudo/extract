# CLI reference

```
extract [options] ARCHIVE|URL...
```

## General

| Flag | Description |
| ---- | ----------- |
| `-v, --verbose` | Verbose logging and tracebacks |
| `-q, --quiet` | Suppress informational output |
| `--no-color` | Disable ANSI colour |
| `--version` | Print version and exit |
| `--help` | Show help, including exit codes |
| `--config` | Show the configuration file path |
| `--verify-install` | Check that the security core is present |

## Extraction

| Flag | Description |
| ---- | ----------- |
| `-d, --directory DIR` | Output directory |
| `-C DIR` | Output directory (short) |
| `-f, --force` | Allow existing output dir / overwrite / duplicate entries |
| `--no-flatten` | Keep a single top-level directory |
| `--keep-junk` | Keep `.DS_Store`, `__MACOSX`, `Thumbs.db` |
| `-r, --recursive` | Extract nested archives |
| `--delete-nested` | Remove nested archives after extraction |
| `--on-error {continue,stop}` | Recursive failure policy |
| `-o, --open` | Open the output directory afterwards |
| `--notify` | Desktop notification on success |
| `--copy-path` | Copy the output path to the clipboard |

## Inspection

| Flag | Description |
| ---- | ----------- |
| `-l, --list` | List members |
| `-i, --info` | Format, sizes, ratio, encryption, counts |
| `-t, --test, --check` | Verify integrity |
| `-n, --dry-run` | Show what would happen |
| `--cat FILE`, `--view FILE` | Write one member to stdout |
| `--search GLOB` | Match member names |
| `--grep PATTERN` | Search text contents |
| `--diff A B` | Compare member lists of two archives |
| `--json` | Structured output (one JSON object per operation) |

## Selection

| Flag | Description |
| ---- | ----------- |
| `-I, --include GLOB` | Extract only matching members (repeatable) |

## Security limits

| Flag | Description |
| ---- | ----------- |
| `--max-size SIZE` | Total uncompressed bytes |
| `--max-file-size SIZE` | Largest single entry |
| `--max-files N` | Maximum entries |
| `--max-ratio N` | Maximum compression ratio |
| `--max-depth N` | Maximum nested depth |
| `--strict` | Fail on symlinks/special files instead of skipping |
| `--no-exec` | Strip execute bits |
| `--allow-symlinks` | Allow links confined to the output directory |
| `--preserve-perms` | Preserve safe mode bits (setuid/setgid stripped) |
| `--insecure` | Allow internal symlinks, skip permission hardening |
| `--sandbox` | Native formats only; never execute external helpers |

## Passwords and checksums

| Flag | Description |
| ---- | ----------- |
| `-p, --password [PASS]` | Password; omit value to prompt |
| `--sha256 HASH` | Verify the archive digest |
| `--verify` | Verify a sidecar `.sha256` if present |
| `--clear-keys` | Delete stored passwords |

## Packing

| Flag | Description |
| ---- | ----------- |
| `-c, --create`, `--pack` | Create an archive: `extract --pack src out.tar.gz` |

Native packing supports `.zip`, `.tar`, `.tar.gz`/`.tgz`, `.tar.bz2`, `.tar.xz`,
and `.gz` (single file).

## Automation

| Flag | Description |
| ---- | ----------- |
| `-j, --jobs N` | Parallel archives |
| `--parallel` | Enable parallel archives |
| `--watch DIR` | Watch a directory and extract new archives |
| `--last` | Show the last extraction |
| `--history` | Show extraction history |

## UI and integrations

| Flag | Description |
| ---- | ----------- |
| `--tui` | Interactive browser |
| `--completion SHELL` | Print completion (bash, zsh, fish, powershell, nushell) |
| `--install-completions` | Install for the current shell |
| `--plugins` | Show the plugin directory |
| `--update` | Print the update command |

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | Success |
| 1 | Extraction or I/O error |
| 2 | Invalid or corrupted archive |
| 3 | Security violation or limit exceeded |
| 4 | Checksum mismatch |
| 5 | Password required or wrong |
| 6 | Unsupported format |

When multiple archives are processed, the highest-severity code is returned.
