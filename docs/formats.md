# Formats

## Native (no external tools)

| Format | Extensions | Notes |
| ------ | ---------- | ----- |
| ZIP | `.zip`, `.cbz`, `.jar`, `.war`, `.ear`, `.apk`, `.epub`, `.docx`, `.xlsx`, `.pptx`, `.whl`, `.nupkg`, ... | ZipCrypto passwords supported |
| TAR | `.tar` | Full POSIX/PAX/GNU headers |
| TAR + GZIP | `.tar.gz`, `.tgz` | |
| TAR + BZIP2 | `.tar.bz2`, `.tbz2`, `.tbz` | |
| TAR + XZ | `.tar.xz`, `.txz` | |
| GZIP | `.gz` | Single stream |
| BZIP2 | `.bz2` | Single stream |
| XZ | `.xz` | Single stream |

Native extraction performs pre-validation, safe writes, link blocking, and
streaming limit enforcement. It also works when the extension lies, because
magic bytes are checked.

## External (optional helpers)

| Format | Helper |
| ------ | ------ |
| 7Z | `7z` / `7za` |
| RAR | `unrar`, `unar`, `7z`, or `bsdtar` |
| ZST / TAR.ZST | `zstd` (and `tar --zstd` for tar) |
| Brotli / TAR.BR | `brotli` |
| LZ4 / TAR.LZ4 | `lz4` |
| LZO | `lzop` |
| DEB | `dpkg-deb` |
| RPM | `rpm2cpio` + `cpio` |
| CPIO | `cpio` |
| AR | `ar` |
| ISO | `bsdtar` or `7z` |
| CAB | `cabextract` or `7z` |

External helpers extract into a private temporary directory. The result is then
validated (names, links, limits) and copied with the native safe-write path.
Nothing is written directly into your destination by the helper.

## Detection

Detection order:

1. Magic bytes for ZIP, GZIP, BZIP2, XZ, ZSTD, 7Z, RAR, LZ4, AR, CPIO.
2. TAR sniffing for compressed streams (`tarfile.is_tarfile`).
3. Extension for formats without reliable magic.

A ZIP renamed to `image.jpg` is still detected as ZIP. A gzip stream containing
a tar is treated as `tar.gz` even if it is named `.gz`.

## Encryption

* Native ZIP: ZipCrypto via `-p PASSWORD` or an interactive prompt.
* External archives: passed to the helper as an argument (never through a
  shell).
* Passwords are not printed. `-p` with no value prompts.
* Optional keyring: `~/.local/share/extract/keys/<sha256(path)>` (mode 0600).
