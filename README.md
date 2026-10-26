# extract

A universal, intelligent, and secure archive extractor for Linux, macOS, and Windows. Everything in one tool.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Features

- **Universal Format Support** - Handles 50+ formats: tar, tar.gz/tgz, tar.bz2/tbz2, tar.xz/txz, tar.zst, zip, 7z, rar, bz2, gz, xz, zst, br, lz4, lzo, deb, rpm, cpio, ar, iso, cab, and more
- **Archive-Aware (Zip/Jar/Docx)** - Works with zip-based formats like .jar, .war, .apk, .epub, .docx, .xlsx, .pptx, .odt, .vsix, .nupkg, etc.
- **Smart Extraction** - Auto-detects format via extension and magic bytes. Flattens unnecessary nested directories automatically
- **Zip-Slip Protection** - Secure by default, blocks path traversal attacks. Use `--insecure` to bypass
- **Cross-Platform** - Works on Linux, macOS, Windows (WSL, Git Bash, PowerShell)
- **Fast & Parallel** - Extract multiple archives concurrently with `--parallel` and `-j/--jobs`
- **Password Support** - Handles encrypted archives with interactive prompts, password flags, and secure keyring storage

## Usage

```bash
# Basic extraction
extract file.zip
x archive.tar.gz

# Extract to specific directory
extract -d ./output file.zip
extract -C ./dir file.tar.gz

# List contents without extracting
extract -l archive.zip

# View a file inside archive
extract --cat README.md archive.zip
x --view config.json file.tar.gz

# Test archive integrity
extract -t archive.zip

# Show archive info
extract -i archive.7z

# Dry run
extract -n file.rar

# Extract from URL
extract https://example.com/file.tar.gz

# Multiple files in parallel
extract file1.zip file2.tar.gz file3.7z --parallel

# Open after extraction
extract -o file.zip

# Recursive extraction of nested archives
extract -r bundle.tar.gz

# Watch directory for new archives
extract --watch ~/Downloads

# Pack/create archives
extract --pack ./folder archive.tar.gz
extract -c ./src backup.zip

# Restore last extraction
extract --last
extract --last --open

# Checksum verification
extract --sha256 abc123... file.zip
extract file.zip  # also checks for .sha256 sidecar

# TUI browser
extract --tui archive.zip

# Diff archives
extract --diff old.zip new.zip
```

## Advanced Options

| Option | Description |
| --- | --- |
| `-v, --verbose` | Show detailed extraction output |
| `-f, --force` | Overwrite existing files/directories |
| `-r, --recursive` | Recursively extract nested archives |
| `-n, --dry-run` | Preview extraction without doing it |
| `-t, --test` | Test archive integrity |
| `-i, --info` | Display archive metadata |
| `--cat FILE` / `--view FILE` | View file contents without extracting |
| `-o, --open` | Open extracted folder in file manager |
| `--json` | Machine-readable JSON output |
| `-p, --password [PASS]` | Password for encrypted archives (`-` for prompt) |
| `--keep-junk` | Keep `__MACOSX`, `.DS_Store`, etc. |
| `--no-flatten` | Don't flatten single-directory archives |
| `--notify` | Send desktop notifications |
| `--copy-path` | Copy extracted path to clipboard |
| `--insecure` | Disable zip-slip protection (not recommended) |
| `--parallel` / `-j N` | Extract multiple archives in parallel |
| `--watch DIR` | Auto-extract new archives in directory |
| `--sha256 HASH` | Verify checksum before extracting |
| `--last` | Show/re-run last extraction |
| `--history` | View extraction history |
| `--clear-keys` | Clear saved passwords from keyring |
| `--tui` | Launch TUI browser |
| `--diff A B` | Compare two archives |
| `-c, --create` / `--pack` | Create/pack archives |
| `--sandbox` | Enable sandboxed extraction (experimental) |

## Shell Integration

### extract-and-cd (`xcd`)

Add to your shell rc for one-command extract and cd:

```bash
xcd() {
    local out
    out=$(extract "$1" 2>&1 | tail -1)
    if [[ "$out" == *"Extracted to"* ]]; then
        local dir=$(echo "$out" | grep -oP 'Extracted to \K.*' | sed 's/ (.*//')
        [ -d "$dir" ] && cd "$dir"
    else
        echo "$out"
    fi
}
```

### Shell Completions

```bash
extract --install-completions
# or
extract --completion bash > ~/.bash_completion.d/extract
```

## Installation

### Quick Install (Linux/macOS/WSL)

```bash
curl -sSL https://raw.githubusercontent.com/neg-sudo/extract/main/scripts/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/neg-sudo/extract/main/install.ps1 | iex
```

### Manual Install

```bash
git clone https://github.com/neg-sudo/extract.git
cd extract
./scripts/install.sh
```

Or install directly:
```bash
cp bin/extract ~/.local/bin/
cp lib/extract.py ~/.extract/lib/
chmod +x ~/.local/bin/extract
```

### Recommended Dependencies

| Platform | Tools |
| --- | --- |
| Linux | `unzip`, `tar`, `gzip`, `bzip2`, `xz-utils` (usually pre-installed). Optional: `p7zip-full`, `unrar`, `zstd`, `brotli`, `lz4` |
| macOS | Pre-installed most. Optional: `brew install p7zip unrar zstd brotli lz4` |
| Windows/WSL | Works great in WSL2. Git Bash needs external tools or WSL utilities |

## Configuration

Config file at `~/.config/extract/config.toml`:

```toml
default_dir = "~/Archives"
flatten = true
keep_junk = false
colors = true
delete_after = false
max_size_gb = 10
zip_slip_protection = true
notify = false
copy_path = false
jobs = 4
```

Project-level config `.extract.toml` in repo root is also supported (merged with precedence).

## Security

- **Zip-Slip Protection** - Enabled by default, validates all archive paths stay within extraction directory
- **Size Limits** - Warns/prevents extraction of extremely large archives (configurable)
- **Secure Password Storage** - Passwords stored with 600 permissions in `~/.local/share/extract/keys/`
- **Sandboxing** - Experimental sandboxed extraction support
- **Checksum Verification** - SHA256 verification for downloads and archives

## Plugin System

Extend with custom format support. Drop plugins in `~/.config/extract/plugins/`:

```python
# ~/.config/extract/plugins/myformat.py
def can_handle(filepath):
    return filepath.endswith('.myext')

def extract(filepath, extract_dir):
    # Custom extraction logic
    return True

def list_contents(filepath):
    return []
```

## Data Locations

| Path | Purpose |
| --- | --- |
| `~/.extract/` | Installation directory |
| `~/.local/bin/extract`, `x` | Executables/aliases |
| `~/.config/extract/` | Configuration & plugins |
| `~/.local/state/extract/history.json` | Extraction history |
| `~/.local/share/extract/keys/` | Encrypted password keyring |

## License

[MIT License](LICENSE) - Copyright (c) 2026 extract contributors

## Version

**v2.0.0** - Universal archive toolkit with security, automation, and productivity features
