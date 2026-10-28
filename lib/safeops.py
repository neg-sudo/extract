#!/usr/bin/env python3
# safeops - security core for extract
# Copyright (c) 2026 extract contributors
# Licensed under MIT License
#
# This module implements the security-critical parts of extract:
#   * decompression-bomb limits (bytes, files, ratio, per-file size)
#   * path sanitization (traversal, absolute paths, drives, UNC)
#   * symlink / hardlink / special-file protection
#   * Windows reserved names, ADS, trailing dots/spaces
#   * Unicode bidirectional / format control rejection
#   * overwrite / duplicate-entry protection
#   * TOCTOU-resistant writes (O_EXCL | O_NOFOLLOW)
#   * permission sanitization
#   * native streaming extraction for zip/tar/gz/bz2/xz using the stdlib
#
# Native extraction here means ZIP, TAR (plain/gz/bz2/xz), GZIP, BZIP2 and XZ
# no longer require external programs. Uncommon formats still fall back to
# external tools in extract.py.

import bz2
import fnmatch
import gzip
import lzma
import os
import re
import stat
import struct
import tarfile
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass

GIB = 1024 ** 3

# Exit codes (stable, documented for CI use)
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID = 2
EXIT_SECURITY = 3
EXIT_CHECKSUM = 4
EXIT_PASSWORD = 5
EXIT_UNSUPPORTED = 6


class ExtractError(Exception):
    exit_code = EXIT_ERROR


class InvalidArchive(ExtractError):
    exit_code = EXIT_INVALID


class SecurityError(ExtractError):
    exit_code = EXIT_SECURITY


class ChecksumError(ExtractError):
    exit_code = EXIT_CHECKSUM


class PasswordRequired(ExtractError):
    exit_code = EXIT_PASSWORD


class UnsupportedFormat(ExtractError):
    exit_code = EXIT_UNSUPPORTED


def human(n):
    """Format a byte count for humans."""
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(n) < 1024.0 or unit == "PiB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024.0


_SIZE_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]?)(i?B?)\s*$", re.I)


def parse_size(value, default=None):
    """Parse '10G', '500M', '1.5GiB', '1024' into bytes."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    m = _SIZE_RE.match(str(value))
    if not m:
        raise ValueError(f"invalid size: {value!r}")
    num = float(m.group(1))
    suffix = m.group(2).upper()
    mult = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3,
            "T": 1024 ** 4, "P": 1024 ** 5, "E": 1024 ** 6}[suffix]
    return int(num * mult)


@dataclass
class Limits:
    max_total: int = 100 * GIB
    max_file: int = 50 * GIB
    max_files: int = 1_000_000
    max_ratio: float = 1000.0
    max_depth: int = 10

    def check_archive(self, count, total, compressed_size, largest):
        if self.max_files and count > self.max_files:
            raise SecurityError(
                f"archive has {count} entries, exceeds --max-files {self.max_files}"
            )
        if self.max_total and total > self.max_total:
            raise SecurityError(
                f"uncompressed size {human(total)} exceeds --max-size {human(self.max_total)}"
            )
        if self.max_file and largest > self.max_file:
            raise SecurityError(
                f"entry size {human(largest)} exceeds --max-file-size {human(self.max_file)}"
            )
        # Ratio only matters once the payload is large enough to be dangerous;
        # tiny, highly-compressible files are normal and not bombs.
        if self.max_ratio and compressed_size > 0 and total >= 64 * 1024 * 1024:
            ratio = total / float(compressed_size)
            if ratio > self.max_ratio:
                raise SecurityError(
                    f"compression ratio {ratio:.1f}:1 exceeds --max-ratio {self.max_ratio:g}:1"
                )


# --- filename sanitization -------------------------------------------------

# Windows device names, matching is case-insensitive and ignores an extension.
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"COM{i}" for i in range(1, 10)
} | {f"LPT{i}" for i in range(1, 10)}

# Unicode bidi override / isolate and other dangerous format controls.
_BIDI_CHARS = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | {0x200E, 0x200F}
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def sanitize_member_name(name, allow_symlinks=False):
    """Validate and normalize an archive member name.

    Returns a safe relative POSIX path. Raises SecurityError otherwise.
    This is deliberately strict: archives that rely on Windows-only or
    bidirectional trickery are rejected rather than silently mangled.
    """
    if name is None:
        raise SecurityError("archive entry has no name")
    if "\x00" in name:
        raise SecurityError("archive entry contains a NUL byte")

    # Reject dangerous Unicode control characters before any normalization.
    for ch in name:
        cp = ord(ch)
        if cp in _BIDI_CHARS:
            raise SecurityError(
                f"archive entry contains a bidirectional/format control character: {name!r}"
            )
        if cp < 0x20 or cp == 0x7F:
            raise SecurityError(f"archive entry contains a control character: {name!r}")

    # Normalize separators.
    norm = name.replace("\\", "/")

    if norm.startswith("/"):
        raise SecurityError(f"absolute path in archive: {name!r}")
    if norm.startswith("//"):
        raise SecurityError(f"UNC path in archive: {name!r}")
    if _DRIVE_RE.match(norm):
        raise SecurityError(f"drive-qualified path in archive: {name!r}")

    parts = []
    for part in norm.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise SecurityError(f"path traversal in archive: {name!r}")
        # Windows alternate data streams and other colon usage.
        if ":" in part:
            raise SecurityError(f"colon (ADS) in archive entry: {name!r}")
        # Windows silently strips trailing dots and spaces.
        if part.rstrip(" .") != part:
            raise SecurityError(f"trailing dot/space in archive entry: {name!r}")
        base = part.split(".", 1)[0].upper()
        if base in _RESERVED:
            raise SecurityError(f"reserved device name in archive entry: {name!r}")
        parts.append(part)

    if not parts:
        raise SecurityError(f"empty path in archive: {name!r}")

    rel = "/".join(parts)
    if len(rel) > 4096:
        raise SecurityError("archive entry path is too long")
    return rel


# --- safe filesystem operations -------------------------------------------

def is_linklike(path):
    """True for symlinks and (on Windows) junctions/reparse points."""
    try:
        if os.path.islink(path):
            return True
        isjunction = getattr(os.path, "isjunction", None)
        return bool(isjunction and isjunction(path))
    except OSError:
        return False


_is_linklike = is_linklike


def collision_key(rel):
    """Key used to detect entries that collide on case-insensitive or
    normalizing filesystems (Windows, default macOS)."""
    return unicodedata.normalize("NFC", rel).casefold()


def _ensure_within(dest_root, path):
    dest_real = os.path.realpath(dest_root)
    path_real = os.path.realpath(path)
    if path_real == dest_real:
        return
    if os.path.commonpath([dest_real, path_real]) != dest_real:
        raise SecurityError(f"path escapes destination directory: {path}")


def prepare_path(dest_root, rel, want_dir=False):
    """Create parent directories safely, refusing to traverse symlinks."""
    parts = rel.split("/")
    if want_dir:
        walk = parts
    else:
        walk = parts[:-1]

    cur = dest_root
    for part in walk:
        cur = os.path.join(cur, part)
        if _is_linklike(cur):
            raise SecurityError(f"refusing to write through symlink/junction: {cur}")
        if os.path.exists(cur):
            if not os.path.isdir(cur):
                raise ExtractError(f"path component is not a directory: {cur}")
        else:
            try:
                os.mkdir(cur, 0o755)
            except FileExistsError:
                if not os.path.isdir(cur) or _is_linklike(cur):
                    raise SecurityError(f"unsafe path component: {cur}")
    target = os.path.join(dest_root, *parts)
    _ensure_within(dest_root, target)
    return target


def open_write(dest_root, rel, force=False):
    """Open a file for writing without following symlinks (O_EXCL|O_NOFOLLOW)."""
    target = prepare_path(dest_root, rel)
    if os.path.lexists(target):
        if _is_linklike(target):
            raise SecurityError(f"refusing to overwrite symlink/junction: {target}")
        if not force:
            raise ExtractError(f"refusing to overwrite existing file: {rel}")
        os.unlink(target)

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags, 0o600)
    except FileExistsError:
        raise ExtractError(f"refusing to overwrite existing file: {rel}")
    except OSError as e:
        if getattr(e, "errno", None) in (40, 62):  # ELOOP
            raise SecurityError(f"symlink loop at: {rel}")
        raise
    return os.fdopen(fd, "wb")


def sanitize_mode(mode, is_dir, no_exec=False, preserve=False):
    """Return safe permission bits. Strips setuid/setgid/sticky always."""
    if preserve:
        base = mode & 0o777
    else:
        base = 0o755 if is_dir else 0o644
        if mode & 0o111 and not is_dir:
            base |= 0o111
    base &= 0o777  # never setuid/setgid/sticky
    if no_exec and not is_dir:
        base &= ~0o111
    return base & 0o777 or (0o755 if is_dir else 0o644)


def validate_symlink_target(dest_root, rel, link_target):
    """Raise SecurityError unless a symlink would stay inside dest_root."""
    target = os.path.join(dest_root, *rel.split("/"))
    link_dir = os.path.dirname(target)
    if os.path.isabs(link_target):
        raise SecurityError(f"absolute symlink target blocked: {rel} -> {link_target}")
    resolved = os.path.normpath(os.path.join(link_dir, link_target))
    _ensure_within(dest_root, resolved)


def make_symlink(dest_root, rel, link_target, force=False):
    """Create a symlink only if its target stays inside dest_root."""
    validate_symlink_target(dest_root, rel, link_target)
    target = prepare_path(dest_root, rel)
    if os.path.lexists(target):
        if not force:
            raise ExtractError(f"refusing to overwrite existing path: {rel}")
        os.unlink(target)
    os.symlink(link_target, target)


# --- archive analysis ------------------------------------------------------

def zip_is_symlink(info):
    return stat.S_ISLNK(info.external_attr >> 16)


def zip_is_encrypted(info):
    return bool(info.flag_bits & 0x1)


def analyze_zip(zf):
    count = 0
    total = 0
    largest = 0
    for info in _zip_infos(zf):
        if info.is_dir():
            continue
        count += 1
        total += info.file_size
        largest = max(largest, info.file_size)
    return count, total, largest


def analyze_tar(members):
    count = 0
    total = 0
    largest = 0
    for m in members:
        if not (m.isfile() or m.islnk()):
            continue
        count += 1
        total += m.size
        largest = max(largest, m.size)
    return count, total, largest


ZIP_PARSE_ERRORS = (zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error,
                    EOFError, UnicodeError, ValueError, OSError,
                    NotImplementedError, struct.error, IndexError, KeyError)
TAR_PARSE_ERRORS = (tarfile.TarError, EOFError, UnicodeError, ValueError,
                    OSError, struct.error, IndexError, KeyError)


def _zip_infos(zf):
    try:
        return zf.infolist()
    except ZIP_PARSE_ERRORS as e:
        raise InvalidArchive(f"invalid or corrupted zip: {e}")


def _tar_members(tf):
    try:
        return tf.getmembers()
    except TAR_PARSE_ERRORS as e:
        raise InvalidArchive(f"invalid or corrupted tar: {e}")


# --- native extraction -----------------------------------------------------

def _copy_limited(src, out, file_limit, total_limit, total_so_far, chunksize=1 << 20):
    written = 0
    while True:
        chunk = src.read(chunksize)
        if not chunk:
            break
        written += len(chunk)
        if file_limit and written > file_limit:
            raise SecurityError("entry exceeds --max-file-size during extraction")
        if total_limit and total_so_far[0] + written > total_limit:
            raise SecurityError("archive exceeds --max-size during extraction")
        out.write(chunk)
    total_so_far[0] += written
    return written


def _match_selectors(rel, selectors):
    if not selectors:
        return True
    for pat in selectors:
        pat = pat.replace("\\", "/")
        if fnmatch.fnmatch(rel, pat) or rel == pat or rel.startswith(pat.rstrip("/") + "/"):
            return True
    return False


def extract_zip(path, dest, limits, *, selectors=None, password=None,
                force=False, no_exec=False, preserve=False,
                allow_symlinks=False, strict=False, want=None):
    """Extract a ZIP archive natively with bounds checking.

    Returns a stats dict. Raises ExtractError subclasses on failure.
    """
    stats = {"files": 0, "dirs": 0, "bytes": 0, "symlinks": 0, "skipped": 0}
    try:
        zf = zipfile.ZipFile(path)
    except ZIP_PARSE_ERRORS as e:
        raise InvalidArchive(f"invalid or corrupted zip: {e}")

    with zf:
        count, total, largest = analyze_zip(zf)
        limits.check_archive(count, total, os.path.getsize(path), largest)

        # Validate everything before writing anything. This prevents partial
        # extraction and any chance of a hostile entry landing on disk.
        entries = []
        seen = set()
        for info in _zip_infos(zf):
            rel = sanitize_member_name(info.filename, allow_symlinks)
            if not info.is_dir():
                key = collision_key(rel)
                if key in seen and not force:
                    raise SecurityError(f"duplicate archive entry: {rel}")
                seen.add(key)
            if zip_is_encrypted(info) and password is None:
                raise PasswordRequired(f"password required for: {rel}")
            if zip_is_symlink(info):
                if not allow_symlinks and strict:
                    raise SecurityError(f"symlink entry blocked: {rel}")
                if allow_symlinks:
                    pwd = (password.encode() if isinstance(password, str)
                           else password)
                    try:
                        raw = zf.read(info, pwd=pwd)
                    except RuntimeError as e:
                        msg = str(e).lower()
                        if "password" in msg or "encrypted" in msg:
                            raise PasswordRequired(f"password required for: {rel}")
                        raise InvalidArchive(f"cannot read {rel}: {e}")
                    except ZIP_PARSE_ERRORS as e:
                        raise InvalidArchive(f"cannot read {rel}: {e}")
                    validate_symlink_target(
                        dest, rel, raw.decode("utf-8", "surrogateescape"))
            entries.append((info, rel))

        total_so_far = [0]
        for info, rel in entries:
            if info.is_dir():
                if _match_selectors(rel, selectors):
                    prepare_path(dest, rel, want_dir=True)
                    stats["dirs"] += 1
                continue

            if not _match_selectors(rel, selectors):
                continue

            if zip_is_symlink(info):
                if not allow_symlinks:
                    if strict:
                        raise SecurityError(f"symlink entry blocked: {rel}")
                    stats["skipped"] += 1
                    continue
                pwd = (password.encode() if isinstance(password, str)
                       else password)
                try:
                    raw = zf.read(info, pwd=pwd)
                except RuntimeError as e:
                    msg = str(e).lower()
                    if "password" in msg or "encrypted" in msg:
                        raise PasswordRequired(f"password required for: {rel}")
                    raise InvalidArchive(f"cannot read {rel}: {e}")
                except ZIP_PARSE_ERRORS as e:
                    raise InvalidArchive(f"cannot read {rel}: {e}")
                make_symlink(dest, rel,
                             raw.decode("utf-8", "surrogateescape"), force=force)
                stats["symlinks"] += 1
                continue

            if zip_is_encrypted(info):
                if password is None:
                    raise PasswordRequired(f"password required for: {rel}")
                pwd = password.encode() if isinstance(password, str) else password
            else:
                pwd = None

            mode = sanitize_mode(info.external_attr >> 16, False, no_exec, preserve)
            try:
                src = zf.open(info, pwd=pwd)
            except RuntimeError as e:
                msg = str(e).lower()
                if "password" in msg or "encrypted" in msg:
                    raise PasswordRequired(f"password required for: {rel}")
                raise InvalidArchive(str(e))
            except ZIP_PARSE_ERRORS as e:
                raise InvalidArchive(f"cannot read {rel}: {e}")
            try:
                with src, open_write(dest, rel, force=force) as out:
                    _copy_limited(src, out, limits.max_file, limits.max_total,
                                  total_so_far)
            except ZIP_PARSE_ERRORS as e:
                raise InvalidArchive(f"cannot extract {rel}: {e}")
            try:
                os.chmod(os.path.join(dest, rel), mode)
            except OSError:
                pass
            stats["files"] += 1

    stats["bytes"] = total_so_far[0]
    return stats


def extract_tar(path, dest, limits, *, selectors=None, force=False,
                no_exec=False, preserve=False, allow_symlinks=False,
                strict=False, want=None):
    """Extract a TAR archive (plain/gz/bz2/xz) natively with bounds checking."""
    stats = {"files": 0, "dirs": 0, "bytes": 0, "symlinks": 0, "skipped": 0}
    try:
        tf = tarfile.open(path, "r:*")
    except TAR_PARSE_ERRORS as e:
        raise InvalidArchive(f"invalid or corrupted tar: {e}")

    with tf:
        members = _tar_members(tf)
        count, total, largest = analyze_tar(members)
        limits.check_archive(count, total, os.path.getsize(path), largest)

        # Validate every member before writing. Unsafe names always abort;
        # symlinks/special files are skipped unless --strict or --allow-symlinks.
        entries = []
        seen = set()
        for m in members:
            rel = sanitize_member_name(m.name, allow_symlinks)
            if not m.isdir():
                key = collision_key(rel)
                if key in seen and not force:
                    raise SecurityError(f"duplicate archive entry: {rel}")
                seen.add(key)
            if m.issym() and allow_symlinks:
                validate_symlink_target(dest, rel, m.linkname)
            if m.issym() and not allow_symlinks and strict:
                raise SecurityError(f"symlink entry blocked: {rel}")
            if m.islnk() and not allow_symlinks and strict:
                raise SecurityError(f"hardlink entry blocked: {rel}")
            if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):
                if strict:
                    raise SecurityError(f"special file blocked: {rel}")
            entries.append((m, rel))

        total_so_far = [0]
        for m, rel in entries:
            if m.isdir():
                if _match_selectors(rel, selectors):
                    prepare_path(dest, rel, want_dir=True)
                    stats["dirs"] += 1
                continue

            if not _match_selectors(rel, selectors):
                continue

            if m.issym():
                if not allow_symlinks:
                    if strict:
                        raise SecurityError(f"symlink entry blocked: {rel}")
                    stats["skipped"] += 1
                    continue
                make_symlink(dest, rel, m.linkname, force=force)
                stats["symlinks"] += 1
                continue

            if m.islnk():
                if not allow_symlinks:
                    if strict:
                        raise SecurityError(f"hardlink entry blocked: {rel}")
                    stats["skipped"] += 1
                    continue
                # Materialize the hardlink as a regular file copied from target.
                try:
                    src = tf.extractfile(m)
                except (KeyError, tarfile.TarError):
                    stats["skipped"] += 1
                    continue
                if src is None:
                    stats["skipped"] += 1
                    continue
                try:
                    with src, open_write(dest, rel, force=force) as out:
                        _copy_limited(src, out, limits.max_file,
                                      limits.max_total, total_so_far)
                except TAR_PARSE_ERRORS as e:
                    raise InvalidArchive(f"cannot extract {rel}: {e}")
                stats["files"] += 1
                continue

            if not m.isfile():
                # Devices, FIFOs, sockets and unknown types are never written.
                if strict:
                    raise SecurityError(f"special file blocked: {rel}")
                stats["skipped"] += 1
                continue

            try:
                src = tf.extractfile(m)
            except (KeyError, tarfile.TarError) as e:
                raise InvalidArchive(f"cannot read {rel}: {e}")
            if src is None:
                stats["skipped"] += 1
                continue

            try:
                with src, open_write(dest, rel, force=force) as out:
                    _copy_limited(src, out, limits.max_file, limits.max_total,
                                  total_so_far)
            except TAR_PARSE_ERRORS as e:
                raise InvalidArchive(f"cannot extract {rel}: {e}")
            try:
                os.chmod(os.path.join(dest, rel),
                         sanitize_mode(m.mode, False, no_exec, preserve))
            except OSError:
                pass
            stats["files"] += 1

    stats["bytes"] = total_so_far[0]
    return stats


def _stream_output_name(path, kind):
    name = os.path.basename(path)
    lower = name.lower()
    for suffix in (".gz", ".bz2", ".xz", ".Z"):
        if lower.endswith(suffix.lower()):
            name = name[: -len(suffix)]
            break
    return name or "output"


def extract_stream(path, dest, kind, limits, *, force=False, no_exec=False):
    """Extract a single compressed stream (gz/bz2/xz) natively."""
    stats = {"files": 0, "dirs": 0, "bytes": 0, "symlinks": 0, "skipped": 0}
    kind = {"gz": "gzip", "gzip": "gzip", "bz2": "bz2", "xz": "xz"}.get(kind)
    if kind is None:
        raise UnsupportedFormat(f"unsupported stream format: {kind}")

    # Discover the original name for gzip when present.
    out_name = _stream_output_name(path, kind)
    if kind == "gzip":
        try:
            with gzip.open(path, "rb") as g:
                original = getattr(g, "_original_name", None)
                if original:
                    out_name = original
        except OSError:
            pass

    rel = sanitize_member_name(out_name)
    rel = rel.split("/")[-1]

    total_so_far = [0]
    opener = {"gzip": gzip.open, "bz2": bz2.open, "xz": lzma.open}[kind]
    try:
        with opener(path, "rb") as src, open_write(dest, rel, force=force) as out:
            _copy_limited(src, out, limits.max_file, limits.max_total,
                          total_so_far)
    except (OSError, EOFError, lzma.LZMAError, zlib.error, ValueError) as e:
        raise InvalidArchive(f"invalid or corrupted {kind} stream: {e}")
    try:
        os.chmod(os.path.join(dest, rel),
                 sanitize_mode(0o644, False, no_exec, False))
    except OSError:
        pass
    stats["files"] = 1
    stats["bytes"] = total_so_far[0]
    return stats


# --- listing / search ------------------------------------------------------

def iter_zip_members(path):
    try:
        with zipfile.ZipFile(path) as zf:
            for info in _zip_infos(zf):
                yield info.filename, info.file_size, info.is_dir()
    except ZIP_PARSE_ERRORS as e:
        raise InvalidArchive(f"invalid or corrupted zip: {e}")


def iter_tar_members(path):
    try:
        with tarfile.open(path, "r:*") as tf:
            for m in _tar_members(tf):
                yield m.name, m.size, m.isdir()
    except TAR_PARSE_ERRORS as e:
        raise InvalidArchive(f"invalid or corrupted tar: {e}")


def search_names(path, kind, pattern):
    """Yield (name, size) whose name matches a glob/substring pattern."""
    gen = iter_zip_members(path) if kind == "zip" else iter_tar_members(path)
    pat = pattern
    for name, size, is_dir in gen:
        if is_dir:
            continue
        if fnmatch.fnmatch(name, pat) or pat in name:
            yield name, size


def grep_contents(path, kind, pattern, *, max_file_bytes=8 * 1024 * 1024,
                  max_total_bytes=64 * 1024 * 1024):
    """Yield (member, lineno, text) for text matches inside an archive.

    Bounded to avoid reading unbounded data from hostile archives.
    """
    needle = pattern.encode() if isinstance(pattern, str) else pattern
    consumed = [0]

    def scan(name, data):
        consumed[0] += len(data)
        if consumed[0] > max_total_bytes:
            return
        if b"\x00" in data[:4096]:
            return  # binary
        for i, line in enumerate(data.splitlines(), 1):
            if needle in line:
                try:
                    yield name, i, line.decode("utf-8", "replace")
                except Exception:
                    yield name, i, repr(line)

    if kind == "zip":
        try:
            zf = zipfile.ZipFile(path)
        except ZIP_PARSE_ERRORS as e:
            raise InvalidArchive(f"invalid or corrupted zip: {e}")
        with zf:
            for info in _zip_infos(zf):
                if info.is_dir() or info.file_size > max_file_bytes:
                    continue
                try:
                    data = zf.read(info)
                except Exception:
                    continue
                yield from scan(info.filename, data)
    else:
        try:
            tf = tarfile.open(path, "r:*")
        except TAR_PARSE_ERRORS as e:
            raise InvalidArchive(f"invalid or corrupted tar: {e}")
        with tf:
            for m in _tar_members(tf):
                if not m.isfile() or m.size > max_file_bytes:
                    continue
                f = tf.extractfile(m)
                if f is None:
                    continue
                try:
                    data = f.read(max_file_bytes)
                finally:
                    f.close()
                yield from scan(m.name, data)
