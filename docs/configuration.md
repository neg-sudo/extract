# Configuration

Configuration lives at `~/.config/extract/config.toml` (a simple `key = value`
format is parsed; full TOML syntax is not required).

```toml
default_dir = "~/Downloads"
flatten = true
keep_junk = false
colors = true
notify = false
copy_path = false
jobs = 4

# security defaults
max_size_gb = 100
max_files = 1000000
max_ratio = 1000
max_depth = 10
no_exec = false
allow_symlinks = false
strict = false
preserve_perms = false
```

Show the path with:

```bash
extract --config
```

Precedence: command-line flags → environment variables → config file →
built-in defaults.

## Relevant environment variables

| Variable | Effect |
| -------- | ------ |
| `EXTRACT_MAX_SIZE` | Total uncompressed bytes |
| `EXTRACT_MAX_FILE_SIZE` | Largest entry |
| `EXTRACT_MAX_FILES` | Entry count |
| `EXTRACT_MAX_RATIO` | Compression ratio |
| `EXTRACT_MAX_DEPTH` | Nested depth |
| `EXTRACT_PYTHON` | Python interpreter for the launcher |
| `EXTRACT_LIB` | Explicit path to `lib/` |
| `HOME` | Location of config, history, keyring |

## State

| Path | Contents |
| ---- | -------- |
| `~/.local/state/extract/history.json` | Last 200 extractions |
| `~/.local/share/extract/keys/` | Optional password cache (mode 0600) |
| `~/.config/extract/plugins/` | Plugin directory |

`extract --history` prints recent entries. `extract --clear-keys` removes the
password cache.
