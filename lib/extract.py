#!/usr/bin/env python3
# extract - The secure, intelligent, cross-platform archive utility
# Copyright (c) 2026 extract contributors
# Licensed under MIT License

import os
import sys
import shutil
import argparse
import subprocess
import platform
import time
import json
import tempfile
import urllib.request
import urllib.parse
import getpass
import hashlib
import tarfile
import zipfile
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None

try:
    import safeops as so
except ImportError:  # pragma: no cover - installed layout fallback
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import safeops as so

VERSION = "3.0.0"


def safe_download_name(url):
    """Derive a safe local filename from a URL."""
    parsed = urllib.parse.urlparse(url)
    name = urllib.parse.unquote(os.path.basename(parsed.path))
    name = name.replace("\\", "_").replace("/", "_")
    try:
        name = so.sanitize_member_name(name)
    except so.ExtractError:
        name = "download"
    return name or "download"


class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

    @staticmethod
    def disable():
        for k in ('RED', 'GREEN', 'YELLOW', 'BLUE', 'MAGENTA', 'CYAN',
                  'BOLD', 'DIM', 'RESET'):
            setattr(Colors, k, '')


class Config:
    def __init__(self):
        self.config_dir = Path.home() / '.config' / 'extract'
        self.config_file = self.config_dir / 'config.toml'
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.defaults = {
            'default_dir': None, 'flatten': True, 'keep_junk': False,
            'colors': True, 'quiet': False, 'delete_after': False,
            'max_size_gb': 100, 'zip_slip_protection': True, 'notify': False,
            'jobs': 4, 'copy_path': False, 'auto_watch': False,
            'sandbox': False, 'max_files': 1000000, 'max_ratio': 1000,
            'max_depth': 10, 'no_exec': False, 'allow_symlinks': False,
            'strict': False, 'preserve_perms': False
        }
        self.load()

    def load(self):
        self.data = self.defaults.copy()
        if self.config_file.exists():
            try:
                content = self.config_file.read_text()
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if v.lower() in ('true', 'false'):
                        self.data[k] = v.lower() == 'true'
                    elif v.lower() == 'none':
                        self.data[k] = None
                    else:
                        try:
                            self.data[k] = float(v) if '.' in v else int(v)
                        except ValueError:
                            self.data[k] = v
            except Exception:
                pass

    def get(self, key, default=None):
        if key in self.data:
            return self.data[key]
        if key in self.defaults:
            return self.defaults[key]
        return default


class History:
    def __init__(self):
        self.state_dir = Path.home() / '.local' / 'state' / 'extract'
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.history_file = self.state_dir / 'history.json'

    def add(self, source, dest, status, arch_type=None):
        try:
            history = []
            if self.history_file.exists():
                history = json.loads(self.history_file.read_text())
            history.append({'timestamp': datetime.now().isoformat(),
                            'source': str(source), 'dest': str(dest),
                            'status': status, 'type': arch_type})
            history = history[-200:]
            self.history_file.write_text(json.dumps(history, indent=2))
        except Exception:
            pass

    def get_last(self):
        try:
            if not self.history_file.exists():
                return None
            history = json.loads(self.history_file.read_text())
            return history[-1] if history else None
        except Exception:
            return None

    def show(self):
        try:
            if not self.history_file.exists():
                print("No history")
                return
            history = json.loads(self.history_file.read_text())
            print(f"{Colors.BOLD}Extraction History{Colors.RESET}")
            for h in reversed(history[-30:]):
                ts = h['timestamp'][:19]
                mark = (f"{Colors.GREEN}✓{Colors.RESET}" if h['status'] == 'ok'
                        else f"{Colors.RED}✗{Colors.RESET}")
                print(f"  {mark} {ts} {Path(h['source']).name} → {h['dest']}")
        except Exception as e:
            print(f"Error: {e}")


class Keyring:
    def __init__(self):
        self.key_dir = Path.home() / '.local' / 'share' / 'extract' / 'keys'
        try:
            self.key_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _path(self, filepath):
        h = hashlib.sha256(Path(filepath).resolve().as_posix().encode()).hexdigest()
        return self.key_dir / h

    def get_key(self, filepath):
        try:
            kf = self._path(filepath)
            if kf.exists():
                return kf.read_text().strip()
        except Exception:
            pass
        return None

    def set_key(self, filepath, password):
        try:
            kf = self._path(filepath)
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            flags |= getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(str(kf), flags, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(password)
            os.chmod(kf, 0o600)
        except Exception:
            pass

    def clear(self):
        try:
            for f in self.key_dir.glob('*'):
                f.unlink()
            print(f"{Colors.GREEN}✓{Colors.RESET} Keys cleared")
        except Exception as e:
            print(f"Error: {e}")


class Spinner:
    def __init__(self, msg):
        self.msg = msg
        self.frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.running = False

    def __enter__(self):
        if not sys.stdout.isatty():
            return self
        self.running = True
        import threading

        def spin():
            i = 0
            while self.running:
                sys.stdout.write(f'\r{Colors.CYAN}{self.frames[i % len(self.frames)]}'
                                 f'{Colors.RESET} {self.msg}')
                sys.stdout.flush()
                i += 1
                time.sleep(0.08)
        self.thread = threading.Thread(target=spin, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.running = False
        time.sleep(0.05)
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        sys.stdout.flush()


class DummySpinner:
    def __init__(self, msg):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Extractor:
    NATIVE_TAR = {'tar', 'tar.gz', 'tar.bz2', 'tar.xz'}
    NATIVE_STREAM = {'gz', 'bz2', 'xz'}
    ZIP_FAMILY = {'zip'}

    def __init__(self, verbose=False, list_only=False, force=False, to_dir=None,
                 quiet=False, dry_run=False, test_only=False, keep_junk=False,
                 no_flatten=False, recursive=False, password=None, cat_file=None,
                 json_output=False, show_info=False, open_after=False, notify=False,
                 insecure=False, jobs=4, copy_path=False, verify=None, sha256=None,
                 limits=None, selectors=None, search=None, grep=None,
                 strict=False, no_exec=False, allow_symlinks=False,
                 preserve_perms=False, delete_nested=False, on_error='continue',
                 max_depth=None, sandbox=False):
        self.verbose = verbose
        self.list_only = list_only
        self.force = force
        self.to_dir = to_dir
        self.quiet = quiet
        self.dry_run = dry_run
        self.test_only = test_only
        self.keep_junk = keep_junk
        self.no_flatten = no_flatten
        self.recursive = recursive
        self.password = password
        self.cat_file = cat_file
        self.json_output = json_output
        self.show_info = show_info
        self.open_after = open_after
        self.notify = notify
        self.insecure = insecure
        self.jobs = jobs
        self.copy_path = copy_path
        self.verify = verify
        self.sha256 = sha256
        self.selectors = selectors or []
        self.search = search
        self.grep = grep
        self.delete_nested = delete_nested
        self.on_error = on_error
        self.exit_code = so.EXIT_OK
        self.warnings = []
        self._visited = set()
        self.config = Config()
        self.history = History()
        self.keyring = Keyring()
        self.os_type = platform.system().lower()
        if self.os_type == 'linux':
            try:
                with open('/proc/version', 'r') as f:
                    if 'microsoft' in f.read().lower():
                        self.os_type = 'wsl'
            except Exception:
                pass

        if limits is None:
            limits = so.Limits(
                max_total=int(self.config.get('max_size_gb') or 100) * 1024 ** 3,
                max_files=int(self.config.get('max_files') or 1_000_000),
                max_ratio=float(self.config.get('max_ratio') or 1000),
                max_depth=int(max_depth if max_depth is not None
                              else (self.config.get('max_depth') or 10)),
            )
        self.limits = limits
        self.strict = strict or bool(self.config.get('strict'))
        self.no_exec = no_exec or bool(self.config.get('no_exec'))
        self.allow_symlinks = (allow_symlinks or bool(self.config.get('allow_symlinks'))
                               or self.insecure)
        self.preserve_perms = preserve_perms or bool(self.config.get('preserve_perms'))
        self.sandbox = sandbox or bool(self.config.get('sandbox'))

        if not sys.stdout.isatty() or self.config.get('colors') is False:
            Colors.disable()

    # --- output helpers ---------------------------------------------------
    def log(self, m):
        if self.verbose and not self.quiet:
            print(f"{Colors.DIM}[extract]{Colors.RESET} {m}", file=sys.stderr)

    def info(self, m):
        if not self.quiet and not self.json_output:
            print(f"{Colors.CYAN}ℹ{Colors.RESET} {m}")

    def success(self, m):
        if not self.quiet and not self.json_output:
            print(f"{Colors.GREEN}✓{Colors.RESET} {m}")

    def warn(self, m):
        self.warnings.append(m)
        if not self.quiet and not self.json_output:
            print(f"{Colors.YELLOW}⚠{Colors.RESET} {m}", file=sys.stderr)

    def error(self, m):
        self.warnings.append(m)
        if not self.json_output:
            print(f"{Colors.RED}✗{Colors.RESET} {m}", file=sys.stderr)

    def _emit(self, obj):
        if self.json_output:
            print(json.dumps(obj, sort_keys=True))

    def _fail(self, exc, filepath=None, arch_type=None):
        code = getattr(exc, 'exit_code', so.EXIT_ERROR)
        self.exit_code = max(self.exit_code, code)
        self.error(str(exc))
        if self.verbose:
            import traceback
            traceback.print_exc()
        return False

    def notify_send(self, title, message):
        if not (self.notify or self.config.get('notify')):
            return
        try:
            if self.os_type == 'darwin':
                subprocess.run(['osascript', '-e',
                                f'display notification "{message}" with title "{title}"'],
                               stdout=subprocess.DEVNULL)
            elif self.os_type in ['linux', 'wsl'] and shutil.which('notify-send'):
                subprocess.run(['notify-send', title, message],
                               stdout=subprocess.DEVNULL)
        except Exception:
            pass

    def copy_to_clipboard(self, text):
        if not (self.copy_path or self.config.get('copy_path')):
            return
        try:
            if self.os_type == 'darwin' and shutil.which('pbcopy'):
                p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
                p.communicate(text.encode())
            elif self.os_type in ['linux', 'wsl']:
                if shutil.which('wl-copy'):
                    p = subprocess.Popen(['wl-copy'], stdin=subprocess.PIPE)
                    p.communicate(text.encode())
                elif shutil.which('xclip'):
                    p = subprocess.Popen(['xclip', '-selection', 'clipboard'],
                                         stdin=subprocess.PIPE)
                    p.communicate(text.encode())
            elif shutil.which('clip'):
                p = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
                p.communicate(text.encode())
            self.log(f"Copied to clipboard: {text}")
        except Exception:
            pass

    # --- checksums --------------------------------------------------------
    def _sha256(self, filepath):
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        return h.hexdigest()

    def verify_checksum(self, filepath):
        if self.sha256:
            try:
                calc = self._sha256(filepath)
                if calc.lower() != self.sha256.lower():
                    raise so.ChecksumError(
                        f"SHA256 mismatch: expected {self.sha256}, got {calc}")
                self.success("SHA256 verified")
                return True
            except so.ChecksumError:
                raise
            except Exception as e:
                raise so.ChecksumError(f"verification failed: {e}")
        for ext in ['.sha256', '.sha256sum', '.sha256.txt']:
            sidecar = filepath + ext
            if os.path.exists(sidecar):
                try:
                    expected = Path(sidecar).read_text().split()[0]
                    calc = self._sha256(filepath)
                    if calc.lower() != expected.lower():
                        raise so.ChecksumError("SHA256 mismatch (sidecar)")
                    self.success("SHA256 verified (sidecar)")
                    return True
                except so.ChecksumError:
                    raise
                except Exception:
                    pass
        return True

    # --- detection --------------------------------------------------------
    def detect_by_magic(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                header = f.read(512)
        except OSError:
            return None
        if header.startswith(b'\x1f\x8b'):
            return 'gz'
        if header.startswith(b'BZh'):
            return 'bz2'
        if header.startswith(b'\xfd7zXZ\x00'):
            return 'xz'
        if header.startswith(b'\x28\xb5\x2f\xfd'):
            return 'zstd'
        if header[:4] in (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'):
            return 'zip'
        if header.startswith((b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00')):
            return 'rar'
        if header.startswith(b'7z\xbc\xaf\x27\x1c'):
            return '7z'
        if header.startswith((b'\x89LZ4', b'\x04\x22\x4d\x18')):
            return 'lz4'
        if header.startswith(b'!<arch>\n'):
            return 'ar'
        if header.startswith(b'070701') or header.startswith(b'070702'):
            return 'cpio'
        return None

    def _is_tar(self, filepath):
        try:
            return tarfile.is_tarfile(filepath)
        except Exception:
            return False

    def detect_type(self, filepath):
        """Return the archive type, preferring content over the extension."""
        base = os.path.basename(filepath).lower()
        ext_type = self._detect_by_extension(base)
        magic = self.detect_by_magic(filepath)

        if magic == 'zip':
            return 'zip'
        if magic in ('gz', 'bz2', 'xz'):
            if self._is_tar(filepath):
                return {'gz': 'tar.gz', 'bz2': 'tar.bz2', 'xz': 'tar.xz'}[magic]
            return magic
        if magic == 'zstd':
            return ext_type if ext_type in ('tar.zst', 'tar.zstd') else 'zst'
        if magic == 'lz4':
            return ext_type if ext_type in ('tar.lz4',) else 'lz4'
        if magic in ('7z', 'rar', 'ar', 'cpio'):
            # Trust magic over a misleading extension for container formats.
            return magic
        if ext_type:
            return ext_type
        return None

    def _detect_by_extension(self, base):
        if base.endswith(('.r00', '.r01')) or '.part1.rar' in base:
            return 'rar'
        if base.endswith(('.z01', '.zip.001')) or '.part1.zip' in base:
            return 'zip'
        if base.endswith(('.tar.gz', '.tgz')):
            return 'tar.gz'
        if base.endswith(('.tar.bz2', '.tbz2', '.tbz')):
            return 'tar.bz2'
        if base.endswith(('.tar.xz', '.txz')):
            return 'tar.xz'
        if base.endswith(('.tar.zst', '.tzst', '.tar.zstd')):
            return 'tar.zst'
        if base.endswith(('.tar.lz', '.tar.lzma', '.tlz')):
            return 'tar.lzma'
        if base.endswith(('.tar.br', '.tar.brotli')):
            return 'tar.br'
        if base.endswith('.tar.lz4'):
            return 'tar.lz4'
        if base.endswith('.tar'):
            return 'tar'
        if base.endswith(('.zip', '.cbz')):
            return 'zip'
        if base.endswith(('.7z', '.7zip', '.cb7')):
            return '7z'
        if base.endswith(('.rar', '.cbr')):
            return 'rar'
        if base.endswith('.bz2'):
            return 'bz2'
        if base.endswith('.gz'):
            return 'gz'
        if base.endswith('.xz'):
            return 'xz'
        if base.endswith(('.zst', '.zstd')):
            return 'zst'
        if base.endswith('.lzma'):
            return 'lzma'
        if base.endswith('.br'):
            return 'brotli'
        if base.endswith('.lz4'):
            return 'lz4'
        if base.endswith('.lzo'):
            return 'lzo'
        if base.endswith('.deb'):
            return 'deb'
        if base.endswith('.rpm'):
            return 'rpm'
        if base.endswith(('.apk', '.ipa', '.xapk', '.aab')):
            return 'zip'
        for e in ['.jar', '.war', '.ear', '.whl', '.egg', '.xpi', '.crx', '.epub',
                  '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.vsix',
                  '.appx', '.msix', '.nupkg', '.kmz']:
            if base.endswith(e):
                return 'zip'
        if base.endswith('.iso'):
            return 'iso'
        if base.endswith('.cab'):
            return 'cab'
        if base.endswith('.arj'):
            return 'arj'
        if base.endswith('.z'):
            return 'compress'
        if base.endswith('.cpio'):
            return 'cpio'
        if base.endswith('.ar'):
            return 'ar'
        if base.endswith('.dmg'):
            return 'dmg'
        return None

    def get_extract_dir(self, filepath):
        path = Path(filepath)
        name = path.name
        base_name = name
        lower = base_name.lower()
        if lower.endswith(('.r00', '.r01')):
            base_name = base_name.rsplit('.r', 1)[0]
            if base_name.lower().endswith('.rar'):
                base_name = base_name[:-4]
        elif lower.endswith('.z01'):
            base_name = base_name[:-4] + '.zip'
            if base_name.lower().endswith('.zip'):
                base_name = base_name[:-4]
        elif lower.endswith('.zip.001'):
            base_name = base_name.replace('.001', '')
            if base_name.lower().endswith('.zip'):
                base_name = base_name[:-4]
        elif '.part1.rar' in lower:
            base_name = base_name.split('.part1.rar')[0]
        elif '.part1.zip' in lower:
            base_name = base_name.split('.part1.zip')[0]

        multi = ['.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst', '.tar.zstd',
                 '.tar.lzma', '.tar.br', '.tar.lz4', '.tgz', '.tbz2', '.tbz',
                 '.txz', '.tzst', '.tlz']
        stripped = False
        for ext in multi:
            if base_name.lower().endswith(ext):
                base_name = base_name[:-len(ext)]
                stripped = True
                break
        if not stripped:
            for ext in ['.tar', '.zip', '.7z', '.rar', '.bz2', '.gz', '.xz',
                        '.zst', '.zstd', '.lzma', '.br', '.lz4', '.lzo', '.cbz',
                        '.cbr', '.cb7', '.jar', '.war', '.ear', '.apk', '.xapk',
                        '.aab', '.ipa', '.epub', '.docx', '.xlsx', '.pptx',
                        '.odt', '.ods', '.odp', '.whl', '.deb', '.rpm', '.cpio',
                        '.iso', '.dmg']:
                if base_name.lower().endswith(ext):
                    base_name = base_name[:-len(ext)]
                    break
        if not stripped and base_name == name and '.' in base_name:
            # Renamed archive (e.g. image.jpg containing a zip).
            base_name = os.path.splitext(base_name)[0]
        if self.to_dir:
            return Path(self.to_dir)
        cfg_dir = self.config.get('default_dir')
        if cfg_dir:
            return Path(cfg_dir).expanduser() / base_name
        return path.parent / (base_name or path.stem or 'extracted')

    def is_url(self, s):
        return s.startswith(('http://', 'https://', 'ftp://'))

    # --- download ---------------------------------------------------------
    def download_url(self, url):
        self.info(f"Downloading {url}")
        filename = safe_download_name(url)
        tmpdir = tempfile.mkdtemp(prefix='extract_')
        dest = os.path.join(tmpdir, filename)
        limit = self.limits.max_total or 0
        try:
            request = urllib.request.Request(
                url, headers={'User-Agent': f'extract/{VERSION}'})
            with Spinner(f"Downloading {filename}"):
                with urllib.request.urlopen(request, timeout=60) as response:
                    length = response.headers.get('Content-Length')
                    if limit and length:
                        try:
                            if int(length) > limit:
                                raise so.SecurityError(
                                    f"download exceeds --max-size "
                                    f"{so.human(limit)}")
                        except ValueError:
                            pass
                    got = 0
                    with open(dest, 'xb') as out:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            got += len(chunk)
                            if limit and got > limit:
                                raise so.SecurityError(
                                    f"download exceeds --max-size "
                                    f"{so.human(limit)}")
                            out.write(chunk)
            self.success(f"Downloaded to {dest}")
            return dest, tmpdir
        except so.ExtractError as e:
            shutil.rmtree(tmpdir, ignore_errors=True)
            self.exit_code = max(self.exit_code,
                                 getattr(e, 'exit_code', so.EXIT_ERROR))
            self.error(f"Download failed: {e}")
            return None, None
        except Exception as e:
            shutil.rmtree(tmpdir, ignore_errors=True)
            self.error(f"Download failed: {e}")
            return None, None

    # --- native helpers ---------------------------------------------------
    def _native_kind(self, arch_type):
        if arch_type == 'zip':
            return 'zip'
        if arch_type in self.NATIVE_TAR:
            return 'tar'
        if arch_type in self.NATIVE_STREAM:
            return arch_type
        return None

    def _extract_native(self, filepath, arch_type, extract_dir):
        kind = self._native_kind(arch_type)
        if kind is None:
            return None
        zf = None
        encrypted = False
        if kind == 'zip':
            try:
                zf = zipfile.ZipFile(filepath)
                encrypted = any(so.zip_is_encrypted(i) for i in zf.infolist())
                zf.close()
            except zipfile.BadZipFile as e:
                raise so.InvalidArchive(f"invalid or corrupted zip: {e}")

        if encrypted and not self.password:
            cached = self.keyring.get_key(filepath)
            if cached:
                self.password = cached
            elif sys.stdin.isatty():
                try:
                    self.password = getpass.getpass('Password: ')
                except (KeyboardInterrupt, EOFError):
                    raise so.PasswordRequired("password required")
            else:
                raise so.PasswordRequired("password required (use -p)")

        try:
            if kind == 'zip':
                return so.extract_zip(
                    filepath, extract_dir, self.limits,
                    selectors=self.selectors, password=self.password,
                    force=self.force, no_exec=self.no_exec,
                    preserve=self.preserve_perms,
                    allow_symlinks=self.allow_symlinks, strict=self.strict)
            if kind == 'tar':
                return so.extract_tar(
                    filepath, extract_dir, self.limits,
                    selectors=self.selectors, force=self.force,
                    no_exec=self.no_exec, preserve=self.preserve_perms,
                    allow_symlinks=self.allow_symlinks, strict=self.strict)
            return so.extract_stream(
                filepath, extract_dir, kind, self.limits,
                force=self.force, no_exec=self.no_exec)
        except so.PasswordRequired:
            if self.password and self.keyring.get_key(filepath) != self.password:
                self.keyring.set_key(filepath, self.password)
            raise

    def _cat_native(self, filepath, arch_type, target):
        kind = self._native_kind(arch_type)
        try:
            if kind == 'zip':
                with zipfile.ZipFile(filepath) as zf:
                    pwd = None
                    if self.password:
                        pwd = self.password.encode()
                    data = zf.read(target, pwd=pwd)
                sys.stdout.buffer.write(data)
                return True
            if kind == 'tar':
                with tarfile.open(filepath, 'r:*') as tf:
                    m = tf.getmember(target)
                    f = tf.extractfile(m)
                    if f is None:
                        raise so.InvalidArchive(f"not a regular file: {target}")
                    shutil.copyfileobj(f, sys.stdout.buffer)
                return True
        except KeyError:
            raise so.InvalidArchive(f"member not found: {target}")
        except RuntimeError as e:
            if 'password' in str(e).lower() or 'encrypted' in str(e).lower():
                raise so.PasswordRequired("password required")
            raise
        return None

    def _list_native(self, filepath, arch_type):
        kind = self._native_kind(arch_type)
        members = []
        if kind == 'zip':
            for name, size, is_dir in so.iter_zip_members(filepath):
                members.append((name, size, is_dir))
        elif kind == 'tar':
            for name, size, is_dir in so.iter_tar_members(filepath):
                members.append((name, size, is_dir))
        else:
            return None

        if self.json_output:
            self._emit({
                'status': 'success', 'archive': filepath, 'format': arch_type,
                'files': sum(1 for _, _, d in members if not d),
                'entries': [{'name': n, 'size': s, 'dir': d}
                            for n, s, d in members],
                'exit_code': 0,
            })
            return True
        self.info(f"Listing {Path(filepath).name} "
                  f"({sum(1 for _, _, d in members if not d)} files)")
        for name, size, is_dir in members:
            if is_dir:
                print(f"{Colors.BLUE}{name}/{Colors.RESET}")
            else:
                print(f"  {name} {Colors.DIM}({so.human(size)}){Colors.RESET}")
        return True

    def _test_native(self, filepath, arch_type):
        kind = self._native_kind(arch_type)
        if kind == 'zip':
            with zipfile.ZipFile(filepath) as zf:
                bad = zf.testzip()
                if bad:
                    raise so.InvalidArchive(f"corrupted member: {bad}")
                return True
        if kind == 'tar':
            with tarfile.open(filepath, 'r:*') as tf:
                for m in tf.getmembers():
                    if not m.isfile():
                        continue
                    f = tf.extractfile(m)
                    if f is None:
                        continue
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
            return True
        if kind in self.NATIVE_STREAM:
            opener = {'gz': so.gzip.open, 'bz2': so.bz2.open,
                      'xz': so.lzma.open}[kind]
            with opener(filepath, 'rb') as f:
                while f.read(1024 * 1024):
                    pass
            return True
        return None

    def _info_native(self, filepath, arch_type):
        kind = self._native_kind(arch_type)
        if kind is None:
            return None
        size = os.path.getsize(filepath)
        if kind == 'zip':
            with zipfile.ZipFile(filepath) as zf:
                count, total, largest = so.analyze_zip(zf)
                encrypted = any(so.zip_is_encrypted(i) for i in zf.infolist())
                compression = 'zip'
        elif kind == 'tar':
            with tarfile.open(filepath, 'r:*') as tf:
                count, total, largest = so.analyze_tar(tf.getmembers())
                encrypted = False
                compression = arch_type
        else:
            return {'status': 'success', 'archive': filepath,
                    'format': arch_type, 'size': size, 'compressed_bytes': size,
                    'files': 1, 'uncompressed_bytes': None,
                    'encrypted': False, 'exit_code': 0}
        return {
            'status': 'success', 'archive': filepath, 'format': arch_type,
            'compression': compression, 'confidence': 99.8,
            'encrypted': encrypted, 'files': count,
            'compressed_bytes': size, 'uncompressed_bytes': total,
            'largest_entry': largest,
            'ratio': round(total / size, 2) if size else None,
            'exit_code': 0,
        }

    # --- external formats -------------------------------------------------
    def _external_command(self, filepath, arch_type, out_dir):
        cmd = None
        if arch_type == 'tar.zst':
            cmd = ['tar', '--zstd', '-xf', filepath, '-C', str(out_dir)]
        elif arch_type == 'tar.lzma':
            cmd = ['tar', '--lzma', '-xf', filepath, '-C', str(out_dir)]
        elif arch_type in ('tar.br', 'tar.lz4'):
            return None
        elif arch_type == 'zip':
            if self.password and shutil.which('7z'):
                cmd = ['7z', 'x', f'-o{out_dir}', f'-p{self.password}', '-y', filepath]
            elif shutil.which('unzip'):
                cmd = ['unzip', '-o', '-q', filepath, '-d', str(out_dir)]
            elif shutil.which('bsdtar'):
                cmd = ['bsdtar', '-xf', filepath, '-C', str(out_dir)]
        elif arch_type == '7z':
            for t in ('7z', '7za', '7zr'):
                if shutil.which(t):
                    cmd = ([t, 'x', f'-o{out_dir}'] +
                           ([f'-p{self.password}'] if self.password else []) +
                           ['-y', filepath])
                    break
            if cmd is None and shutil.which('bsdtar'):
                cmd = ['bsdtar', '-xf', filepath, '-C', str(out_dir)]
        elif arch_type == 'rar':
            for t in ('unrar', 'unar', '7z', 'bsdtar'):
                if not shutil.which(t):
                    continue
                if t == 'unrar':
                    cmd = [t, 'x', '-o+', filepath, str(out_dir) + '/']
                    if self.password:
                        cmd.insert(2, '-p' + self.password)
                    else:
                        cmd.insert(2, '-p-')
                elif t == 'unar':
                    cmd = [t, '-o', str(out_dir), '-force-overwrite', filepath]
                    if self.password:
                        cmd += ['-password', self.password]
                elif t == '7z':
                    cmd = ([t, 'x', f'-o{out_dir}'] +
                           ([f'-p{self.password}'] if self.password else []) +
                           ['-y', filepath])
                else:
                    cmd = [t, '-xf', filepath, '-C', str(out_dir)]
                break
        elif arch_type == 'zst':
            tool = 'zstd' if shutil.which('zstd') else 'unzstd'
            if shutil.which(tool):
                cmd = [tool, '-d', '-c', filepath]
        elif arch_type == 'brotli':
            if shutil.which('brotli'):
                cmd = ['brotli', '-d', '-c', filepath]
        elif arch_type == 'lz4':
            if shutil.which('lz4'):
                cmd = ['lz4', '-d', '-c', filepath]
        elif arch_type == 'lzo':
            if shutil.which('lzop'):
                cmd = ['lzop', '-d', '-c', filepath]
        elif arch_type == 'deb' and shutil.which('dpkg-deb'):
            cmd = ['dpkg-deb', '-x', filepath, str(out_dir)]
        elif arch_type == 'rpm':
            return None
        elif arch_type == 'cpio' and shutil.which('cpio'):
            cmd = ['cpio', '-idmv', '--quiet', '-I', os.path.abspath(filepath)]
        elif arch_type == 'ar' and shutil.which('ar'):
            cmd = ['ar', 'x', os.path.abspath(filepath)]
        elif arch_type == 'iso':
            if shutil.which('bsdtar'):
                cmd = ['bsdtar', '-xf', filepath, '-C', str(out_dir)]
        elif arch_type == 'cab':
            if shutil.which('cabextract'):
                cmd = ['cabextract', '-d', str(out_dir), filepath]
            elif shutil.which('7z'):
                cmd = ['7z', 'x', f'-o{out_dir}', '-y', filepath]
        return cmd

    def _limit_external(self):
        """Return a preexec_fn that caps helper output file size on POSIX."""
        if resource is None:
            return None

        def _apply():
            try:
                if self.limits.max_file:
                    _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
                    cap = self.limits.max_file
                    if hard != resource.RLIM_INFINITY:
                        cap = min(cap, hard)
                    resource.setrlimit(resource.RLIMIT_FSIZE, (cap, hard))
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            except (ValueError, OSError, AttributeError):
                pass

        return _apply

    def _import_tree(self, tmp, dest, compressed_size=None):
        """Validate a helper's temp tree, then import it through safe writes."""
        stats = {'files': 0, 'dirs': 0, 'bytes': 0, 'symlinks': 0, 'skipped': 0}
        entries = []
        seen = set()
        count = 0
        total = 0
        largest = 0

        # Pass 1: validate every name, link target, duplicate and limit before
        # writing anything into the destination.
        for root, dirs, files in os.walk(tmp, topdown=True, followlinks=False):
            for d in list(dirs):
                p = os.path.join(root, d)
                rel = os.path.relpath(p, tmp).replace(os.sep, '/')
                if so.is_linklike(p):
                    dirs.remove(d)
                    try:
                        rel_s = so.sanitize_member_name(rel, self.allow_symlinks)
                    except so.SecurityError:
                        stats['skipped'] += 1
                        continue
                    if not self.allow_symlinks:
                        stats['skipped'] += 1
                        continue
                    target = os.readlink(p)
                    so.validate_symlink_target(dest, rel_s, target)
                    entries.append(('link', rel_s, target))
                    continue
                rel_s = so.sanitize_member_name(rel)
                key = so.collision_key(rel_s)
                if key in seen and not self.force:
                    raise so.SecurityError(f"duplicate archive entry: {rel_s}")
                seen.add(key)
                entries.append(('dir', rel_s))

            for f in files:
                p = os.path.join(root, f)
                rel = os.path.relpath(p, tmp).replace(os.sep, '/')
                rel_s = so.sanitize_member_name(rel, self.allow_symlinks)
                key = so.collision_key(rel_s)
                if key in seen and not self.force:
                    raise so.SecurityError(f"duplicate archive entry: {rel_s}")
                seen.add(key)
                if so.is_linklike(p):
                    if not self.allow_symlinks:
                        stats['skipped'] += 1
                        continue
                    target = os.readlink(p)
                    so.validate_symlink_target(dest, rel_s, target)
                    entries.append(('link', rel_s, target))
                    continue
                if not os.path.isfile(p):
                    stats['skipped'] += 1
                    continue
                size = os.path.getsize(p)
                count += 1
                total += size
                largest = max(largest, size)
                entries.append(('file', rel_s, p, size))

        self.limits.check_archive(count, total,
                                  compressed_size or 0, largest)

        # Pass 2: import through the same safe primitives as native formats.
        for entry in entries:
            kind, rel_s = entry[0], entry[1]
            if kind == 'dir':
                so.prepare_path(dest, rel_s, want_dir=True)
                stats['dirs'] += 1
            elif kind == 'link':
                so.make_symlink(dest, rel_s, entry[2], force=self.force)
                stats['symlinks'] += 1
            else:
                src_path, size = entry[2], entry[3]
                with open(src_path, 'rb') as src, \
                        so.open_write(dest, rel_s, force=self.force) as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
                try:
                    os.chmod(os.path.join(dest, rel_s),
                             so.sanitize_mode(os.stat(src_path).st_mode, False,
                                              self.no_exec, self.preserve_perms))
                except OSError:
                    pass
                stats['files'] += 1
        stats['bytes'] = total
        return stats

    def _blocked_external(self, arch_type):
        if self.sandbox:
            raise so.UnsupportedFormat(
                f"--sandbox: external helper required for {arch_type}")

    def _extract_external(self, filepath, arch_type, extract_dir):
        self._blocked_external(arch_type)
        if arch_type == 'rpm':
            if not (shutil.which('rpm2cpio') and shutil.which('cpio')):
                raise so.UnsupportedFormat("rpm requires rpm2cpio and cpio")
            tmp = tempfile.mkdtemp(prefix='extract_', dir=str(extract_dir.parent))
            preexec = self._limit_external()
            try:
                p1 = subprocess.Popen(['rpm2cpio', filepath],
                                      stdout=subprocess.PIPE,
                                      preexec_fn=preexec)
                p2 = subprocess.Popen(['cpio', '-idmv', '--quiet'],
                                      stdin=p1.stdout, cwd=tmp,
                                      preexec_fn=preexec)
                p1.stdout.close()
                p2.communicate()
                if p2.returncode != 0:
                    raise so.ExtractError("rpm extraction failed")
                return self._import_tree(tmp, extract_dir,
                                         os.path.getsize(filepath))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        tmp = tempfile.mkdtemp(prefix='extract_', dir=str(extract_dir.parent))
        preexec = self._limit_external()
        try:
            cmd = self._external_command(filepath, arch_type, tmp)
            if cmd is None:
                raise so.UnsupportedFormat(
                    f"no native support and no external tool for {arch_type}")
            output = None
            if arch_type in ('zst', 'brotli', 'lz4', 'lzo'):
                out_name = Path(filepath).stem
                out_path = os.path.join(tmp, out_name)
                with open(out_path, 'wb') as out:
                    result = subprocess.run(cmd, stdout=out,
                                            stderr=subprocess.PIPE,
                                            preexec_fn=preexec)
                if result.returncode != 0:
                    raise so.InvalidArchive(
                        result.stderr.decode(errors='ignore').strip() or
                        f"{arch_type} extraction failed")
            else:
                result = subprocess.run(
                    cmd, stdout=subprocess.DEVNULL if not self.verbose else None,
                    stderr=subprocess.PIPE,
                    cwd=tmp if arch_type in ('cpio', 'ar') else None,
                    preexec_fn=preexec)
                if result.returncode != 0:
                    err = result.stderr.decode(errors='ignore')
                    if ('password' in err.lower() or 'encrypted' in err.lower()):
                        raise so.PasswordRequired("password required or wrong")
                    raise so.InvalidArchive(err.strip() or
                                            f"{arch_type} extraction failed")
            return self._import_tree(tmp, extract_dir,
                                     os.path.getsize(filepath))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # --- operations -------------------------------------------------------
    def get_archive_info(self, filepath):
        arch_type = self.detect_type(filepath)
        if not arch_type:
            raise so.UnsupportedFormat("unknown archive format")
        info = self._info_native(filepath, arch_type)
        if info is None:
            size = os.path.getsize(filepath)
            info = {'status': 'success', 'archive': filepath,
                    'format': arch_type, 'size': size,
                    'compressed_bytes': size, 'exit_code': 0}
        if self.json_output:
            self._emit(info)
            return True
        self.info(f"{Colors.BOLD}Archive Info{Colors.RESET}")
        print(f"  File: {filepath}")
        print(f"  Format: {arch_type}")
        if info.get('confidence'):
            print(f"  Confidence: {info['confidence']}%")
        if info.get('files') is not None:
            print(f"  Files: {info['files']:,}")
        if info.get('compressed_bytes') is not None:
            print(f"  Compressed: {so.human(info['compressed_bytes'])}")
        if info.get('uncompressed_bytes') is not None:
            print(f"  Uncompressed: {so.human(info['uncompressed_bytes'])}")
        if info.get('ratio') is not None:
            print(f"  Ratio: {info['ratio']}:1")
        if 'encrypted' in info:
            print(f"  Encrypted: {'yes' if info['encrypted'] else 'no'}")
        print(f"  Protection: {'on' if not self.insecure else 'bypassed (--insecure)'}")
        return True

    def test_archive(self, filepath):
        arch_type = self.detect_type(filepath)
        if not self.json_output:
            self.info(f"Testing {Path(filepath).name}...")
        try:
            ok = self._test_native(filepath, arch_type)
            if ok is None:
                self._blocked_external(arch_type)
                cmd = None
                if arch_type == 'zip' and shutil.which('unzip'):
                    cmd = ['unzip', '-t', filepath]
                elif arch_type == '7z':
                    for t in ('7z', '7za'):
                        if shutil.which(t):
                            cmd = [t, 't', filepath]
                            break
                elif arch_type == 'rar' and shutil.which('unrar'):
                    cmd = ['unrar', 't', filepath]
                if cmd is None:
                    raise so.UnsupportedFormat(f"cannot test {arch_type}")
                result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE)
                ok = result.returncode == 0
                if not ok:
                    raise so.InvalidArchive("archive is corrupted")
            if self.json_output:
                self._emit({'status': 'success', 'archive': filepath,
                            'integrity': 'ok', 'exit_code': 0})
            else:
                self.success("Archive is OK")
            return True
        except so.ExtractError as e:
            if self.json_output:
                self._emit({'status': 'error', 'archive': filepath,
                            'error': str(e), 'exit_code': getattr(e, 'exit_code', 1)})
            return self._fail(e, filepath, arch_type)
        except Exception as e:
            return self._fail(so.InvalidArchive(str(e)), filepath, arch_type)

    def dry_run_extract(self, filepath):
        arch_type = self.detect_type(filepath)
        extract_dir = self.get_extract_dir(filepath)
        size = os.path.getsize(filepath)
        if self.json_output:
            self._emit({'status': 'success', 'dry_run': True,
                        'archive': filepath, 'format': arch_type, 'size': size,
                        'output': str(extract_dir), 'exit_code': 0})
            return True
        self.info(f"{Colors.BOLD}Dry run{Colors.RESET}")
        print(f"  Source: {filepath}")
        print(f"  Format: {arch_type}")
        print(f"  Size: {so.human(size)}")
        print(f"  Target: {extract_dir}")
        print(f"  Limits: files≤{self.limits.max_files:,}, "
              f"size≤{so.human(self.limits.max_total)}, "
              f"file≤{so.human(self.limits.max_file)}, "
              f"ratio≤{self.limits.max_ratio:g}:1, depth≤{self.limits.max_depth}")
        return True

    def search_archive(self, filepath):
        arch_type = self.detect_type(filepath)
        kind = self._native_kind(arch_type)
        if kind not in ('zip', 'tar'):
            raise so.UnsupportedFormat(
                f"search requires native zip/tar support, not {arch_type}")
        shown = 0
        if self.search:
            for name, size in so.search_names(filepath, kind, self.search):
                shown += 1
                if self.json_output:
                    self._emit({'status': 'success', 'archive': filepath,
                                'match': name, 'size': size, 'exit_code': 0})
                else:
                    print(f"{name} {Colors.DIM}({so.human(size)}){Colors.RESET}")
        if self.grep:
            for name, lineno, text in so.grep_contents(filepath, kind, self.grep):
                shown += 1
                if self.json_output:
                    self._emit({'status': 'success', 'archive': filepath,
                                'match': name, 'line': lineno, 'text': text,
                                'exit_code': 0})
                else:
                    print(f"{Colors.BOLD}{name}{Colors.RESET}:{lineno}: {text}")
        if not shown and not self.json_output:
            self.warn("no matches")
        self.exit_code = so.EXIT_OK
        return shown > 0

    def smart_extract(self, filepath, original_source=None, depth=0):
        start = time.time()
        filepath = os.path.abspath(filepath)
        result = {'status': 'error', 'archive': filepath,
                  'exit_code': so.EXIT_ERROR, 'warnings': self.warnings}
        if not os.path.exists(filepath):
            return self._fail(so.ExtractError(f"file not found: {filepath}"))
        try:
            arch_type = self.detect_type(filepath)
            if not arch_type:
                raise so.UnsupportedFormat(f"unknown archive format: {filepath}")
            result['format'] = arch_type
            self.verify_checksum(filepath)

            if self.cat_file:
                ok = self._cat_native(filepath, arch_type, self.cat_file)
                if ok is None:
                    self._blocked_external(arch_type)
                    cmd = None
                    if arch_type == 'zip':
                        cmd = ['unzip', '-p', filepath, self.cat_file]
                    elif arch_type == '7z':
                        for t in ('7z', '7za'):
                            if shutil.which(t):
                                cmd = [t, 'e', '-so', filepath, self.cat_file]
                                break
                    elif arch_type == 'rar' and shutil.which('unrar'):
                        cmd = ['unrar', 'p', '-inul', filepath, self.cat_file]
                    if cmd is None:
                        raise so.UnsupportedFormat(
                            f"cannot cat from {arch_type}")
                    ok = subprocess.run(cmd).returncode == 0
                return ok

            if self.test_only:
                return self.test_archive(filepath)
            if self.show_info:
                return self.get_archive_info(filepath)
            if self.dry_run:
                return self.dry_run_extract(filepath)
            if self.search or self.grep:
                return self.search_archive(filepath)
            if self.list_only:
                if not self.json_output:
                    self.info(f"Listing {Path(filepath).name}")
                ok = self._list_native(filepath, arch_type)
                if ok is None:
                    return self.list_archive_no_native(filepath, arch_type)
                return ok

            extract_dir = self.get_extract_dir(filepath)
            if extract_dir.exists() and not self.force:
                raise so.ExtractError(
                    f"output directory exists: {extract_dir} (use -f)")
            created = not extract_dir.exists()
            extract_dir.mkdir(parents=True, exist_ok=True)

            try:
                with Spinner("Extracting...") if not self.json_output else DummySpinner(""):
                    stats = self._extract_native(filepath, arch_type, extract_dir)
                    if stats is None:
                        stats = self._extract_external(filepath, arch_type,
                                                       extract_dir)
            except Exception:
                if created:
                    shutil.rmtree(extract_dir, ignore_errors=True)
                raise

            if not self.no_flatten and self.config.get('flatten', True):
                self._flatten_if_needed(extract_dir)
            if not self.keep_junk and not self.config.get('keep_junk', False):
                self._remove_junk(extract_dir)

            elapsed = time.time() - start
            result.update({
                'status': 'success', 'output': str(extract_dir),
                'files': stats.get('files', 0),
                'directories': stats.get('dirs', 0),
                'bytes_written': stats.get('bytes', 0),
                'skipped': stats.get('skipped', 0),
                'duration_ms': int(elapsed * 1000),
                'exit_code': so.EXIT_OK,
            })
            self._emit(result)
            if not self.json_output:
                self.success(f"Extracted to {Colors.BOLD}{extract_dir}{Colors.RESET} "
                             f"{Colors.DIM}({stats.get('files', 0)} files, "
                             f"{so.human(stats.get('bytes', 0))}, "
                             f"{elapsed:.2f}s){Colors.RESET}")
            self.history.add(original_source or filepath, str(extract_dir),
                             'ok', arch_type)
            self.notify_send('extract', f'Extracted {Path(filepath).name}')
            self.copy_to_clipboard(str(extract_dir))
            if self.open_after:
                self._open_folder(extract_dir)
            if self.recursive:
                self._extract_recursive(extract_dir, depth + 1)
            return True

        except so.ExtractError as e:
            result['error'] = str(e)
            result['exit_code'] = getattr(e, 'exit_code', so.EXIT_ERROR)
            self._emit(result)
            return self._fail(e, filepath)
        except KeyboardInterrupt:
            self.warn("cancelled")
            self.exit_code = max(self.exit_code, so.EXIT_ERROR)
            return False
        except Exception as e:
            result['error'] = str(e)
            self._emit(result)
            return self._fail(so.ExtractError(str(e)), filepath)

    def list_archive_no_native(self, filepath, arch_type):
        self._blocked_external(arch_type)
        cmd = None
        if arch_type in ('7z',):
            for t in ('7z', '7za'):
                if shutil.which(t):
                    cmd = [t, 'l', filepath]
                    break
        elif arch_type == 'rar':
            if shutil.which('unrar'):
                cmd = ['unrar', 'l', filepath]
            elif shutil.which('unar'):
                cmd = ['unar', '-t', filepath]
        if cmd is None and shutil.which('bsdtar'):
            cmd = ['bsdtar', '-tf', filepath]
        if cmd is None:
            raise so.UnsupportedFormat(f"cannot list {arch_type}")
        if self.json_output:
            result = subprocess.run(cmd, stdout=subprocess.PIPE)
            self._emit({'status': 'success', 'archive': filepath,
                        'format': arch_type, 'listing':
                        result.stdout.decode(errors='ignore'), 'exit_code': 0})
        else:
            subprocess.run(cmd)
        return True

    def _open_folder(self, path):
        try:
            if self.os_type == 'darwin':
                subprocess.run(['open', str(path)], stdout=subprocess.DEVNULL)
            elif self.os_type == 'linux':
                subprocess.run(['xdg-open', str(path)], stdout=subprocess.DEVNULL)
            elif self.os_type == 'wsl':
                if shutil.which('wslview'):
                    subprocess.run(['wslview', str(path)], stdout=subprocess.DEVNULL)
                else:
                    subprocess.run(['explorer.exe',
                                    str(path).replace('/mnt/c', 'C:').replace('/', '\\')],
                                   stdout=subprocess.DEVNULL)
            elif self.os_type == 'windows':
                subprocess.run(['explorer', str(path)], stdout=subprocess.DEVNULL)
        except Exception:
            pass

    def _extract_recursive(self, dir_path, depth=1):
        if depth > self.limits.max_depth:
            self.warn(f"recursion depth limit ({self.limits.max_depth}) reached")
            return
        found = []
        for root, dirs, files in os.walk(dir_path, followlinks=False):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    if os.path.islink(fp):
                        continue
                    rp = os.path.realpath(fp)
                    if rp in self._visited:
                        continue
                    if self.detect_type(fp):
                        self._visited.add(rp)
                        found.append(fp)
                except OSError:
                    continue
        if not found:
            return
        self.info(f"Found {len(found)} nested archive(s) (depth {depth})")
        for af in found:
            prefix = "  " * depth
            if not self.json_output:
                print(f"{prefix}├─ {Path(af).name}")
            adir = self.get_extract_dir(af)
            if adir.exists() and not self.force:
                self.warn(f"nested output exists, skipping: {adir}")
                continue
            created = not adir.exists()
            adir.mkdir(parents=True, exist_ok=True)
            atype = self.detect_type(af)
            try:
                stats = self._extract_native(af, atype, adir)
                if stats is None:
                    stats = self._extract_external(af, atype, adir)
                if not self.no_flatten:
                    self._flatten_if_needed(adir)
                if not self.keep_junk:
                    self._remove_junk(adir)
                if self.delete_nested:
                    try:
                        os.remove(af)
                    except OSError:
                        pass
                if not self.json_output:
                    print(f"{prefix}│  └─ {stats.get('files', 0)} files")
                self._extract_recursive(adir, depth + 1)
            except so.ExtractError as e:
                if created:
                    shutil.rmtree(adir, ignore_errors=True)
                self.warn(f"nested extraction failed for {af}: {e}")
                self.exit_code = max(self.exit_code, getattr(e, 'exit_code', 1))
                if self.on_error == 'stop':
                    raise

    # --- maintenance ------------------------------------------------------
    def _remove_junk(self, extract_dir):
        for root, dirs, files in os.walk(extract_dir, topdown=False):
            for f in files:
                if f in ('__MACOSX', '.DS_Store', 'Thumbs.db', 'desktop.ini'):
                    try:
                        os.remove(os.path.join(root, f))
                    except OSError:
                        pass
            for d in dirs:
                if d == '__MACOSX':
                    try:
                        shutil.rmtree(os.path.join(root, d))
                    except OSError:
                        pass

    def _flatten_if_needed(self, extract_dir):
        try:
            items = [i for i in extract_dir.iterdir()
                     if i.name not in ('__MACOSX', '.DS_Store')]
            if len(items) == 1 and items[0].is_dir() and not items[0].is_symlink():
                subdir = items[0]
                if any(i.is_symlink() for i in subdir.iterdir()):
                    # Moving symlinks up a level can change their target.
                    return
                for item in subdir.iterdir():
                    dest = extract_dir / item.name
                    if dest.exists() and not self.force:
                        continue
                    try:
                        shutil.move(str(item), str(dest))
                    except OSError:
                        pass
                try:
                    subdir.rmdir()
                except OSError:
                    pass
        except OSError:
            pass


def diff_archives(a, b, extractor):
    def members(p):
        t = extractor.detect_type(p)
        kind = extractor._native_kind(t)
        if kind == 'zip':
            return {n for n, s, d in so.iter_zip_members(p) if not d}
        if kind == 'tar':
            return {n for n, s, d in so.iter_tar_members(p) if not d}
        raise so.UnsupportedFormat(f"diff requires native zip/tar, not {t}")
    left = members(a)
    right = members(b)
    only_a = sorted(left - right)
    only_b = sorted(right - left)
    if extractor.json_output:
        extractor._emit({'status': 'success', 'only_in_a': only_a,
                         'only_in_b': only_b, 'exit_code': 0})
        return True
    print(f"{Colors.BOLD}Diff{Colors.RESET} {Path(a).name} ↔ {Path(b).name}")
    for n in only_a:
        print(f"{Colors.RED}- {n}{Colors.RESET}")
    for n in only_b:
        print(f"{Colors.GREEN}+ {n}{Colors.RESET}")
    if not only_a and not only_b:
        print("  identical member lists")
    return True


def generate_completions(shell):
    opts = ("-v --verbose -l --list -f --force -d --directory -C -n --dry-run "
            "-t --test --check -i --info -r --recursive -p --password --cat "
            "--view -o --open --json --keep-junk --no-flatten --notify "
            "--insecure -j --jobs --parallel --tui -c --create --pack -q "
            "--quiet --no-color --sha256 --verify --copy-path --max-size "
            "--max-file-size --max-files --max-ratio --max-depth --include "
            "--search --grep --strict --no-exec --allow-symlinks "
            "--preserve-perms --delete-nested --on-error --version --help")
    if shell == 'bash':
        return f'''# extract bash completion
_extract_completions() {{
    local cur prev opts
    COMPREPLY=(); cur="${{COMP_WORDS[COMP_CWORD]}}"; prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    opts="{opts}"
    [[ ${{cur}} == -* ]] && {{ COMPREPLY=( $(compgen -W "${{opts}}" -- ${{cur}}) ); return 0; }}
    COMPREPLY=( $(compgen -f -X '!*.@(tar|tgz|tar.gz|tbz2|tar.bz2|txz|tar.xz|tzst|tar.zst|zip|7z|rar|bz2|gz|xz|zst|br|lz4|deb|rpm|iso|jar|war|apk|epub|docx|xlsx|pptx|cbz|cbr|xapk|dmg)' -- ${{cur}}) )
}}
complete -F _extract_completions extract x
'''
    if shell == 'zsh':
        return f'''#compdef extract x
_extract() {{
    local -a opts
    opts=({opts})
    _arguments "*:files:_files -g '*.(tar|tgz|tar.gz|tbz2|tar.bz2|txz|tar.xz|tzst|tar.zst|zip|7z|rar|bz2|gz|xz|zst|br|lz4|deb|rpm|iso|jar|war|apk|epub|docx|xlsx|pptx|dmg)'" \\
        '1: :->files' '*:: :->args'
    case $state in
        files) _files -g '*.(tar|tgz|tar.gz|zip|7z|rar|gz|xz|bz2|zst)' ;;
        args) _describe 'option' opts ;;
    esac
}}
compdef _extract extract x
'''
    if shell == 'fish':
        lines = []
        for opt in ("verbose v", "list l", "force f", "dry-run n", "test t",
                    "info i", "recursive r", "open o", "json", "quiet q",
                    "tui", "version"):
            parts = opt.split()
            flag = f"-l {parts[0]}" if len(parts) == 1 else f"-s {parts[1]} -l {parts[0]}"
            lines.append(f"complete -c extract {flag}")
        lines.append("complete -c extract -f -a \"(__fish_complete_suffix .zip .tar .tar.gz .tgz .7z .rar .gz .xz .bz2 .zst)\"")
        lines.append("complete -c x -w extract")
        return "\n".join(lines) + "\n"
    if shell == 'powershell':
        return f'''# extract PowerShell completion
Register-ArgumentCompleter -Native -CommandName extract,x -ScriptBlock {{
    param($wordToComplete, $commandAst, $cursorPosition)
    $opts = '{opts}'.Split(' ')
    $opts | Where-Object {{ $_ -like "$wordToComplete*" }} | ForEach-Object {{
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterName', $_)
    }}
}}
'''
    if shell == 'nushell':
        return '''# extract Nushell completion
export extern extract [
    ...files: path
    --verbose(-v) --list(-l) --force(-f) --dry-run(-n) --test(-t)
    --info(-i) --recursive(-r) --json --quiet(-q) --tui
    --max-size: string --max-file-size: string --max-files: int
    --max-ratio: float --max-depth: int --include: string
    --search: string --grep: string --strict --no-exec
    --allow-symlinks --preserve-perms
]
'''
    return ''


def launch_tui(filepath):
    """Minimal but real archive browser (curses), with a plain fallback."""
    try:
        import curses
    except ImportError:
        curses = None

    extractor = Extractor(list_only=True)
    arch_type = extractor.detect_type(filepath)
    kind = extractor._native_kind(arch_type)
    if kind == 'zip':
        members = [n for n, s, d in so.iter_zip_members(filepath) if not d]
    elif kind == 'tar':
        members = [n for n, s, d in so.iter_tar_members(filepath) if not d]
    else:
        print(f"{Colors.YELLOW}⚠{Colors.RESET} TUI supports native zip/tar only")
        print(f"{Colors.DIM}Use --list for {arch_type}{Colors.RESET}")
        return

    if not members:
        print("Archive is empty")
        return

    if curses is None or not sys.stdout.isatty():
        for n in members:
            print(n)
        return

    selected = set()
    query = ""

    def run(stdscr):
        nonlocal query
        curses.curs_set(0)
        idx = 0
        top = 0
        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            visible = [m for m in members if query.lower() in m.lower()]
            if not visible:
                visible = members
            idx = max(0, min(idx, len(visible) - 1))
            if idx < top:
                top = idx
            if idx >= top + h - 4:
                top = idx - (h - 4) + 1
            title = f" {Path(filepath).name}  [{len(visible)}/{len(members)}] "
            stdscr.addnstr(0, 0, title.ljust(w), w, curses.A_REVERSE)
            stdscr.addnstr(1, 0, f" /{query}   selected: {len(selected)}".ljust(w),
                           w, curses.A_DIM)
            for row, name in enumerate(visible[top:top + h - 4]):
                y = row + 2
                mark = "[x]" if name in selected else "[ ]"
                attr = curses.A_REVERSE if top + row == idx else curses.A_NORMAL
                stdscr.addnstr(y, 0, f" {mark} {name}".ljust(w), w, attr)
            help_line = " ↑↓ move  space select  a all  / search  E extract  q quit "
            stdscr.addnstr(h - 2, 0, help_line.ljust(w), w, curses.A_REVERSE)
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in (ord('q'), 27):
                return
            if ch in (curses.KEY_UP, ord('k')):
                idx = max(0, idx - 1)
            elif ch in (curses.KEY_DOWN, ord('j')):
                idx = min(len(visible) - 1, idx + 1)
            elif ch == curses.KEY_PPAGE:
                idx = max(0, idx - (h - 4))
            elif ch == curses.KEY_NPAGE:
                idx = min(len(visible) - 1, idx + (h - 4))
            elif ch == ord(' '):
                name = visible[idx]
                if name in selected:
                    selected.discard(name)
                else:
                    selected.add(name)
                idx = min(len(visible) - 1, idx + 1)
            elif ch == ord('a'):
                if len(selected) == len(members):
                    selected.clear()
                else:
                    selected.update(members)
            elif ch == ord('/'):
                curses.curs_set(1)
                stdscr.addnstr(h - 1, 0, "search: ".ljust(w), w)
                stdscr.refresh()
                buf = ""
                while True:
                    c = stdscr.getch()
                    if c in (10, 13, curses.KEY_ENTER):
                        break
                    if c == 27:
                        buf = ""
                        break
                    if c in (curses.KEY_BACKSPACE, 127, 8):
                        buf = buf[:-1]
                    elif 32 <= c < 127:
                        buf += chr(c)
                    stdscr.addnstr(h - 1, 0, ("search: " + buf).ljust(w), w)
                    stdscr.refresh()
                curses.curs_set(0)
                query = buf
                idx = 0
                top = 0
            elif ch in (ord('e'), ord('E')):
                targets = selected or {visible[idx]}
                out = extractor.get_extract_dir(filepath)
                if out.exists() and not extractor.force:
                    extractor.force = True
                out.mkdir(parents=True, exist_ok=True)
                if kind == 'tar':
                    stats = so.extract_tar(filepath, out, extractor.limits,
                                           selectors=sorted(targets),
                                           force=True,
                                           no_exec=extractor.no_exec,
                                           allow_symlinks=extractor.allow_symlinks)
                else:
                    stats = so.extract_zip(filepath, out, extractor.limits,
                                           selectors=sorted(targets),
                                           password=extractor.password,
                                           force=True,
                                           no_exec=extractor.no_exec,
                                           allow_symlinks=extractor.allow_symlinks)
                return sorted(targets), str(out), stats

    try:
        result = curses.wrapper(run)
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.RESET} TUI error: {e}")
        return
    if result:
        targets, out, stats = result
        print(f"{Colors.GREEN}✓{Colors.RESET} Extracted {stats.get('files', 0)} "
              f"file(s) to {out}")


def pack_archive(sources, output):
    print(f"{Colors.BOLD}Packing{Colors.RESET} -> {output}")
    try:
        lower = output.lower()
        if lower.endswith('.zip'):
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
                for src in sources:
                    p = Path(src)
                    if p.is_dir():
                        for root, dirs, files in os.walk(p):
                            for f in files:
                                fp = os.path.join(root, f)
                                if os.path.islink(fp):
                                    continue
                                zf.write(fp, os.path.relpath(fp, p.parent))
                    elif p.is_file():
                        zf.write(str(p), p.name)
        else:
            mode = None
            for suffix, m in (('.tar.gz', 'w:gz'), ('.tgz', 'w:gz'),
                              ('.tar.bz2', 'w:bz2'), ('.tbz2', 'w:bz2'),
                              ('.tar.xz', 'w:xz'), ('.txz', 'w:xz'),
                              ('.tar', 'w')):
                if lower.endswith(suffix):
                    mode = m
                    break
            if mode:
                with tarfile.open(output, mode) as tf:
                    for src in sources:
                        tf.add(src, arcname=os.path.basename(src.rstrip('/')))
            elif lower.endswith('.gz') and len(sources) == 1:
                import gzip
                with open(sources[0], 'rb') as fi, gzip.open(output, 'wb') as fo:
                    shutil.copyfileobj(fi, fo)
            else:
                raise so.UnsupportedFormat(
                    "native packing supports .zip, .tar, .tar.gz/.tgz, "
                    ".tar.bz2, .tar.xz, .gz")
        print(f"{Colors.GREEN}✓{Colors.RESET} Created {output}")
        return True
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.RESET} {e}")
        return False


def watch_directory(dir_path, extractor):
    print(f"{Colors.BOLD}Watching{Colors.RESET} {dir_path} for archives...")
    print(f"{Colors.DIM}Press Ctrl+C to stop{Colors.RESET}")
    seen = set()
    try:
        while True:
            for f in Path(dir_path).glob('*'):
                if f.is_file() and f.suffix.lower() in [
                        '.zip', '.tar', '.gz', '.xz', '.bz2', '.7z', '.rar',
                        '.zst', '.tgz', '.tbz2', '.txz']:
                    key = (str(f), f.stat().st_mtime)
                    if key not in seen:
                        seen.add(key)
                        time.sleep(1)
                        print(f"\n{Colors.CYAN}New archive:{Colors.RESET} {f.name}")
                        extractor.smart_extract(str(f))
            time.sleep(2)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Stopped watching{Colors.RESET}")


def build_limits(args):
    return so.Limits(
        max_total=so.parse_size(args.max_size) if args.max_size
        else int(os.environ.get('EXTRACT_MAX_SIZE', 0) or 100) * 1024 ** 3,
        max_file=so.parse_size(args.max_file_size) if args.max_file_size
        else so.parse_size(os.environ.get('EXTRACT_MAX_FILE_SIZE') or '50G'),
        max_files=args.max_files if args.max_files is not None
        else int(os.environ.get('EXTRACT_MAX_FILES', 0) or 1_000_000),
        max_ratio=args.max_ratio if args.max_ratio is not None
        else float(os.environ.get('EXTRACT_MAX_RATIO', 0) or 1000),
        max_depth=args.max_depth if args.max_depth is not None
        else int(os.environ.get('EXTRACT_MAX_DEPTH', 0) or 10),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='extract',
        description=f'{Colors.BOLD}extract{Colors.RESET} {VERSION} - '
                    'The secure, intelligent, cross-platform archive utility',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""security limits:
  --max-size 10G        maximum total uncompressed bytes
  --max-file-size 2G    maximum size of a single entry
  --max-files 100000    maximum number of entries
  --max-ratio 100       maximum compression ratio
  --max-depth 10        maximum nested-archive recursion depth

exit codes:
  0 success   1 extraction error   2 invalid archive   3 security violation
  4 checksum mismatch   5 password required   6 unsupported format
""")
    parser.add_argument('files', nargs='*', help='Archive/URL/files')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-l', '--list', action='store_true')
    parser.add_argument('-f', '--force', action='store_true')
    parser.add_argument('-d', '--directory', metavar='DIR')
    parser.add_argument('-C', dest='dir', metavar='DIR')
    parser.add_argument('-n', '--dry-run', action='store_true')
    parser.add_argument('-t', '--test', '--check', dest='test', action='store_true')
    parser.add_argument('-i', '--info', action='store_true')
    parser.add_argument('-r', '--recursive', action='store_true')
    parser.add_argument('-p', '--password', metavar='PASS', nargs='?', const='-')
    parser.add_argument('--cat', dest='cat_file', metavar='FILE')
    parser.add_argument('--view', dest='cat_file', metavar='FILE')
    parser.add_argument('-o', '--open', action='store_true')
    parser.add_argument('--json', action='store_true', dest='json_output')
    parser.add_argument('--keep-junk', action='store_true')
    parser.add_argument('--no-flatten', action='store_true')
    parser.add_argument('--notify', action='store_true')
    parser.add_argument('--insecure', action='store_true')
    parser.add_argument('--copy-path', action='store_true')
    parser.add_argument('-j', '--jobs', type=int, default=4)
    parser.add_argument('--parallel', action='store_true')
    parser.add_argument('--tui', action='store_true')
    parser.add_argument('-c', '--create', action='store_true')
    parser.add_argument('--pack', action='store_true')
    parser.add_argument('--watch', metavar='DIR', help='Watch directory for archives')
    parser.add_argument('--sha256', metavar='HASH')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--diff', nargs=2, metavar=('A', 'B'))
    parser.add_argument('--sandbox', action='store_true')
    parser.add_argument('--last', action='store_true')
    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('--no-color', action='store_true')

    sec = parser.add_argument_group('security limits')
    sec.add_argument('--max-size', metavar='SIZE',
                     help='maximum total uncompressed bytes (e.g. 10G)')
    sec.add_argument('--max-file-size', metavar='SIZE',
                     help='maximum size of a single entry (e.g. 2G)')
    sec.add_argument('--max-files', type=int, metavar='N')
    sec.add_argument('--max-ratio', type=float, metavar='R')
    sec.add_argument('--max-depth', type=int, metavar='N')
    sec.add_argument('--strict', action='store_true',
                     help='abort on unsafe entries instead of skipping them')
    sec.add_argument('--no-exec', action='store_true',
                     help='strip execute permission bits')
    sec.add_argument('--allow-symlinks', action='store_true',
                     help='allow symlinks/hardlinks that stay inside output')
    sec.add_argument('--preserve-perms', action='store_true',
                     help='preserve safe mode bits (setuid/setgid always stripped)')

    sel = parser.add_argument_group('selection and search')
    sel.add_argument('-I', '--include', action='append', metavar='GLOB',
                     help='extract only members matching GLOB (repeatable)')
    sel.add_argument('--search', metavar='PATTERN',
                     help='list members whose name matches PATTERN')
    sel.add_argument('--grep', metavar='PATTERN',
                     help='search text contents of members')
    sel.add_argument('--delete-nested', action='store_true',
                     help='delete nested archives after recursive extraction')
    sel.add_argument('--on-error', choices=['continue', 'stop'], default='continue')

    parser.add_argument('--completion',
                        choices=['bash', 'zsh', 'fish', 'powershell', 'nushell'])
    parser.add_argument('--install-completions', action='store_true')
    parser.add_argument('--config', action='store_true')
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--clear-keys', action='store_true')
    parser.add_argument('--update', action='store_true')
    parser.add_argument('--plugins', action='store_true')
    parser.add_argument('--verify-install', action='store_true')
    parser.add_argument('--version', action='version',
                        version=f'extract {VERSION}')
    args = parser.parse_args(argv)

    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    if args.completion:
        print(generate_completions(args.completion))
        sys.exit(0)
    if args.install_completions:
        home = Path.home()
        shell = os.path.basename(os.environ.get('SHELL', ''))
        targets = {
            'bash': home / '.bash_completion.d/extract',
            'zsh': home / '.zsh/completions/_extract',
            'fish': home / '.config/fish/completions/extract.fish',
        }
        if shell in targets:
            p = targets[shell]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(generate_completions(shell))
            print(f"Installed to {p}")
        else:
            print(f"Unknown shell: {shell or '(unset)'}")
        sys.exit(0)
    if args.config:
        cfg = Config()
        print(f"Config: {cfg.config_file}")
        print("zip_slip_protection = true")
        print("max_size_gb = 100")
        print("max_files = 1000000")
        print("max_ratio = 1000")
        print("max_depth = 10")
        print("no_exec = false")
        print("allow_symlinks = false")
        print("strict = false")
        sys.exit(0)
    if args.history:
        History().show()
        sys.exit(0)
    if args.clear_keys:
        Keyring().clear()
        sys.exit(0)
    if args.verify_install:
        core_ok = all(hasattr(so, name) for name in (
            'sanitize_member_name', 'extract_zip', 'extract_tar',
            'extract_stream', 'Limits'))
        print(f"extract {VERSION}")
        print(f"python: {platform.python_version()}")
        print(f"security core: {'ok' if core_ok else 'MISSING'}")
        print("native: zip tar gz bz2 xz")
        sys.exit(0 if core_ok else so.EXIT_ERROR)
    if args.update:
        print("curl -sSL https://raw.githubusercontent.com/neg-sudo/extract/main/"
              "scripts/install.sh | bash")
        sys.exit(0)
    if args.plugins:
        pdir = Path.home() / '.config/extract/plugins'
        pdir.mkdir(parents=True, exist_ok=True)
        print(f"Plugins dir: {pdir}")
        print("Place *.py files exposing can_handle(path) and extract(path, dest)")
        sys.exit(0)
    if args.tui and args.files:
        launch_tui(args.files[0])
        sys.exit(0)
    if (args.create or args.pack) and args.files:
        if len(args.files) >= 2:
            ok = pack_archive(args.files[:-1], args.files[-1])
            sys.exit(0 if ok else so.EXIT_ERROR)
        print("Usage: extract --pack src... out.tar.gz")
        sys.exit(so.EXIT_ERROR)
    if args.watch:
        watch_directory(args.watch, Extractor(notify=True))
        sys.exit(0)
    if args.last:
        h = History().get_last()
        if not h:
            print("No history")
            sys.exit(so.EXIT_ERROR)
        print(f"Last: {h['source']} -> {h['dest']}")
        sys.exit(0)
    if not args.files and not args.cat_file and not args.diff:
        parser.print_help()
        sys.exit(so.EXIT_ERROR)
    if args.password == '-':
        try:
            args.password = getpass.getpass('Password: ')
        except Exception:
            pass

    limits = build_limits(args)
    ext = Extractor(
        verbose=args.verbose, list_only=args.list, force=args.force,
        to_dir=args.dir or args.directory, quiet=args.quiet,
        dry_run=args.dry_run, test_only=args.test, keep_junk=args.keep_junk,
        no_flatten=args.no_flatten, recursive=args.recursive,
        password=args.password, cat_file=args.cat_file,
        json_output=args.json_output, show_info=args.info,
        open_after=args.open, notify=args.notify, insecure=args.insecure,
        jobs=args.jobs, copy_path=args.copy_path, sha256=args.sha256,
        limits=limits, selectors=args.include, search=args.search,
        grep=args.grep, strict=args.strict, no_exec=args.no_exec,
        allow_symlinks=args.allow_symlinks,
        preserve_perms=args.preserve_perms,
        delete_nested=args.delete_nested, on_error=args.on_error,
        max_depth=args.max_depth, sandbox=args.sandbox)

    if args.diff:
        try:
            diff_archives(args.diff[0], args.diff[1], ext)
            sys.exit(ext.exit_code)
        except so.ExtractError as e:
            ext.error(str(e))
            sys.exit(getattr(e, 'exit_code', 1))

    if (len(args.files) > 1 and (args.parallel or args.jobs > 1)
            and not args.json_output and not args.list):
        ok_count = 0
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {executor.submit(ext.smart_extract, f, f): f
                       for f in args.files}
            for fut in as_completed(futures):
                try:
                    if fut.result():
                        ok_count += 1
                except Exception:
                    pass
        if not args.quiet:
            print(f"\n{Colors.GREEN}{ok_count}/{len(args.files)}"
                  f"{Colors.RESET} completed")
        sys.exit(ext.exit_code if ok_count != len(args.files) else 0)

    ok_count = 0
    for f in args.files:
        if ext.is_url(f):
            dest, tmpdir = ext.download_url(f)
            if dest:
                if ext.smart_extract(dest, f):
                    ok_count += 1
                try:
                    shutil.rmtree(tmpdir)
                except Exception:
                    pass
            else:
                ext.exit_code = max(ext.exit_code, so.EXIT_ERROR)
        else:
            if ext.smart_extract(f, f):
                ok_count += 1
    if len(args.files) > 1 and not args.quiet and not args.json_output:
        print(f"\n{Colors.GREEN}{ok_count}/{len(args.files)}"
              f"{Colors.RESET} completed")
    if ext.exit_code:
        sys.exit(ext.exit_code)
    sys.exit(0 if ok_count == len(args.files) else so.EXIT_ERROR)


if __name__ == '__main__':
    main()
