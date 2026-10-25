# extract

A universal, intelligent archive extractor for Linux, macOS, and Windows (WSL/Git Bash).

## Features

- **One command for everything** - Handles tar, zip, 7z, rar, gz, bz2, xz, zst, and many more
- **Smart extraction** - Automatically extracts to a clean folder named after the archive, avoids unnecessary nesting
- **Cross-platform** - Works on Linux, macOS, and Windows (via WSL, Git Bash, or Cygwin)
- **Auto-detection** - Uses both file extensions and magic bytes to identify formats
- **Handles complex formats** - Supports .jar, .war, .apk, .docx, .xlsx, .epub, .deb, .rpm, and more
- **List mode** - Preview archive contents without extracting
- **Overwrite control** - Safely handles existing files
- **Minimal dependencies** - Uses native tools where available, falls back gracefully

## Supported Formats

| Format | Extensions | Notes |
| --- | --- | --- |
| Tarball (gzip) | `.tar.gz`, `.tgz` | Native |
| Tarball (bzip2) | `.tar.bz2`, `.tbz2`, `.tbz` | Native |
| Tarball (xz) | `.tar.xz`, `.txz` | Native |
| Tarball (zstd) | `.tar.zst`, `.tzst` | Requires `zstd` |
| Tar | `.tar` | Native |
| ZIP | `.zip`, `.jar`, `.war`, `.apk`, `.whl`, `.xpi`, `.crx`, `.epub`, `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.vsix` | Native via `unzip` |
| 7-Zip | `.7z` | Requires `7z`/`p7zip` |
| RAR | `.rar` | Requires `unrar` |
| Compressed files | `.gz`, `.bz2`, `.xz`, `.zst`, `.br`, `.lz4`, `.lzma` | Auto-handled |
| Package formats | `.deb`, `.rpm`, `.cpio` | Platform-specific tools |
| Others | `.iso`, `.cab`, `.arj`, `.ace`, `.z` | Tool-dependent |

## Installation

### Quick Install (Linux/macOS)
```bash
curl -sSL https://raw.githubusercontent.com/yourusername/extract/main/install.sh | bash
```

### Manual Install
```bash
git clone https://github.com/yourusername/extract.git
cd extract
sudo cp bin/extract /usr/local/bin/
sudo chmod +x /usr/local/bin/extract
```

Or install to `~/.local/bin` without sudo:
```bash
cp bin/extract ~/.local/bin/
chmod +x ~/.local/bin/extract
```

### Windows
Use with [WSL](https://learn.microsoft.com/en-us/windows/wsl/), [Git Bash](https://gitforwindows.org/), or [MSYS2](https://www.msys2.org/). The script will auto-detect and use Windows-native tools when available.

## Usage

```bash
# Extract an archive (auto-detects format)
extract file.zip
extract archive.tar.gz
x file.7z  # short alias

# Extract to specific directory
extract -d ./output file.zip
extract -C ./dir file.tar.gz

# List contents without extracting
extract -l archive.zip

# Verbose output
extract -v archive.tar.xz

# Force overwrite
extract -f archive.zip

# Extract multiple files
extract file1.zip file2.tar.gz file3.7z
```

## Cross-Platform Notes

- **macOS**: Most formats work out of the box. Install additional tools via `brew` if needed (`brew install p7zip unrar zstd brotli lz4`)
- **Linux**: Usually has `tar`, `gzip`, `unzip` pre-installed. Install extras as needed via package manager
- **Windows/WSL**: Works best in WSL2. In Git Bash, will fall back to available Windows tools or WSL utilities
- **Git Bash/Cygwin**: Some archive formats may require additional packages

## License

MIT License - see [LICENSE](LICENSE) for details.
