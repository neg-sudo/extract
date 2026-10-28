# Installation

## One-line install (Unix)

```bash
curl -fsSL https://raw.githubusercontent.com/neg-sudo/extract/main/scripts/install.sh | bash
```

Installs into `~/.extract` and links `~/.local/bin/extract` and
`~/.local/bin/x`. Override with:

```bash
EXTRACT_INSTALL_DIR=~/.local/share/extract \
EXTRACT_BIN_DIR=~/.local/bin \
  curl -fsSL .../scripts/install.sh | bash
```

Source downloads are atomic: a failed request cannot truncate a working
installation.

## Windows

```powershell
irm https://raw.githubusercontent.com/neg-sudo/extract/main/install.ps1 | iex
```

## Prebuilt binaries

Tagged releases publish standalone binaries for:

* Linux x86_64 and ARM64
* macOS x86_64 and ARM64
* Windows x86_64 and ARM64
* a universal `extract.pyz` zipapp

Each release includes `SHA256SUMS`, an optional GPG signature, and an optional
Sigstore signature. Verify before running:

```bash
sha256sum -c SHA256SUMS
gpg --verify SHA256SUMS.asc SHA256SUMS
```

## From source

```bash
git clone https://github.com/neg-sudo/extract.git
cd extract
./bin/extract --version
python3 -m unittest discover -s tests -v
```

Install with pip (provides `extract` and `x`):

```bash
pip install .
```

## Requirements

* Python 3.9 or newer for the source install.
* No third-party Python packages.
* Optional external tools for uncommon formats: `7z`, `unrar`, `zstd`,
  `brotli`, `lz4`, `cabextract`, `dpkg-deb`, `rpm2cpio` + `cpio`, `cpio`, `ar`.

Native formats — ZIP, TAR, TAR.GZ, TAR.BZ2, TAR.XZ, GZ, BZ2, XZ — never need
external programs.

## Shell completions

```bash
extract --install-completions
# or print one:
extract --completion bash > /etc/bash_completion.d/extract
```

Supported: Bash, Zsh, Fish, PowerShell, Nushell. Ready-made files live in
[`completions/`](https://github.com/neg-sudo/extract/tree/main/completions).
