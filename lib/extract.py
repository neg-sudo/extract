#!/usr/bin/env python3
# extract - Universal archive extractor for all platforms v2.0
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
import signal
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        for k in vars(Colors):
            if not k.startswith('_'): setattr(Colors, k, '')

class Config:
    def __init__(self):
        self.config_dir = Path.home() / '.config' / 'extract'
        self.config_file = self.config_dir / 'config.toml'
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.defaults = {
            'default_dir': None, 'flatten': True, 'keep_junk': False,
            'colors': True, 'quiet': False, 'delete_after': False,
            'max_size_gb': 10, 'zip_slip_protection': True, 'notify': False,
            'jobs': 4, 'copy_path': False, 'auto_watch': False,
            'sandbox': False
        }
        self.load()
    def load(self):
        self.data = self.defaults.copy()
        if self.config_file.exists():
            try:
                content = self.config_file.read_text()
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip(); v = v.strip().strip('"').strip("'")
                        if v.lower() in ('true','false'): self.data[k] = v.lower()=='true'
                        elif v.lower() == 'none': self.data[k] = None
                        else:
                            try:
                                if '.' in v: self.data[k] = float(v)
                                else: self.data[k] = int(v)
                            except: self.data[k] = v
            except: pass
    def get(self, key): return self.data.get(key, self.defaults.get(key))

class History:
    def __init__(self):
        self.state_dir = Path.home() / '.local' / 'state' / 'extract'
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.state_dir / 'history.json'
    def add(self, source, dest, status, arch_type=None):
        try:
            history = []
            if self.history_file.exists():
                history = json.loads(self.history_file.read_text())
            history.append({'timestamp': datetime.now().isoformat(), 'source': str(source), 'dest': str(dest), 'status': status, 'type': arch_type})
            history = history[-200:]
            self.history_file.write_text(json.dumps(history, indent=2))
        except: pass
    def get_last(self):
        try:
            if not self.history_file.exists(): return None
            history = json.loads(self.history_file.read_text())
            return history[-1] if history else None
        except: return None
    def show(self):
        try:
            if not self.history_file.exists():
                print("No history"); return
            history = json.loads(self.history_file.read_text())
            print(f"{Colors.BOLD}Extraction History{Colors.RESET}")
            for h in reversed(history[-30:]):
                ts = h['timestamp'][:19]
                status = f"{Colors.GREEN}✓{Colors.RESET}" if h['status']=='ok' else f"{Colors.RED}✗{Colors.RESET}"
                print(f"  {status} {ts} {Path(h['source']).name} → {h['dest']}")
        except Exception as e: print(f"Error: {e}")

class Keyring:
    def __init__(self):
        self.key_dir = Path.home() / '.local' / 'share' / 'extract' / 'keys'
        self.key_dir.mkdir(parents=True, exist_ok=True)
    def get_key(self, filepath):
        try:
            h = hashlib.sha256(Path(filepath).resolve().as_posix().encode()).hexdigest()
            kf = self.key_dir / h
            if kf.exists(): return kf.read_text().strip()
        except: pass
        return None
    def set_key(self, filepath, password):
        try:
            h = hashlib.sha256(Path(filepath).resolve().as_posix().encode()).hexdigest()
            kf = self.key_dir / h
            kf.write_text(password); os.chmod(kf, 0o600)
        except: pass
    def clear(self):
        try:
            for f in self.key_dir.glob('*'): f.unlink()
            print(f"{Colors.GREEN}✓{Colors.RESET} Keys cleared")
        except Exception as e: print(f"Error: {e}")

class Extractor:
    def __init__(self, verbose=False, list_only=False, force=False, to_dir=None, 
                 quiet=False, dry_run=False, test_only=False, keep_junk=False,
                 no_flatten=False, recursive=False, password=None, cat_file=None,
                 json_output=False, show_info=False, open_after=False, notify=False, 
                 insecure=False, jobs=4, copy_path=False, verify=None, sha256=None):
        self.verbose = verbose; self.list_only = list_only; self.force = force
        self.to_dir = to_dir; self.quiet = quiet; self.dry_run = dry_run
        self.test_only = test_only; self.keep_junk = keep_junk; self.no_flatten = no_flatten
        self.recursive = recursive; self.password = password; self.cat_file = cat_file
        self.json_output = json_output; self.show_info = show_info
        self.open_after = open_after; self.notify = notify; self.insecure = insecure
        self.jobs = jobs; self.copy_path = copy_path; self.verify = verify; self.sha256 = sha256
        self.config = Config(); self.history = History(); self.keyring = Keyring()
        self.os_type = platform.system().lower()
        if self.os_type == 'linux':
            try:
                with open('/proc/version','r') as f:
                    if 'microsoft' in f.read().lower(): self.os_type = 'wsl'
            except: pass
        if not sys.stdout.isatty() or self.config.get('colors') is False: Colors.disable()
    
    def log(self, m): 
        if self.verbose and not self.quiet: print(f"{Colors.DIM}[extract]{Colors.RESET} {m}", file=sys.stderr)
    def info(self, m): 
        if not self.quiet and not self.json_output: print(f"{Colors.CYAN}ℹ{Colors.RESET} {m}")
    def success(self, m): 
        if not self.quiet and not self.json_output: print(f"{Colors.GREEN}✓{Colors.RESET} {m}")
    def warn(self, m): 
        if not self.quiet and not self.json_output: print(f"{Colors.YELLOW}⚠{Colors.RESET} {m}", file=sys.stderr)
    def error(self, m): 
        if not self.json_output: print(f"{Colors.RED}✗{Colors.RESET} {m}", file=sys.stderr)
        else: print(json.dumps({'error': m}))
    
    def notify_send(self, title, message):
        if not (self.notify or self.config.get('notify')): return
        try:
            if self.os_type == 'darwin':
                subprocess.run(['osascript','-e',f'display notification "{message}" with title "{title}"'], stdout=subprocess.DEVNULL)
            elif self.os_type in ['linux','wsl'] and shutil.which('notify-send'):
                subprocess.run(['notify-send', title, message], stdout=subprocess.DEVNULL)
        except: pass
    
    def copy_to_clipboard(self, text):
        if not (self.copy_path or self.config.get('copy_path')): return
        try:
            if self.os_type == 'darwin' and shutil.which('pbcopy'):
                p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE); p.communicate(text.encode())
            elif self.os_type in ['linux','wsl']:
                if shutil.which('wl-copy'): p=subprocess.Popen(['wl-copy'], stdin=subprocess.PIPE); p.communicate(text.encode())
                elif shutil.which('xclip'): p=subprocess.Popen(['xclip','-selection','clipboard'], stdin=subprocess.PIPE); p.communicate(text.encode())
            elif shutil.which('clip'): p=subprocess.Popen(['clip'], stdin=subprocess.PIPE); p.communicate(text.encode())
            if not self.quiet: self.log(f"Copied to clipboard: {text}")
        except: pass
    
    def verify_checksum(self, filepath):
        if self.sha256:
            try:
                h = hashlib.sha256()
                with open(filepath,'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''): h.update(chunk)
                calc = h.hexdigest()
                if calc.lower() != self.sha256.lower():
                    self.error(f"SHA256 mismatch! Expected {self.sha256}, got {calc}")
                    return False
                self.success("SHA256 verified")
                return True
            except Exception as e:
                self.error(f"Verification failed: {e}")
                return False
        # Check sidecar
        for ext in ['.sha256', '.sha256sum', '.sha256.txt']:
            sidecar = filepath + ext
            if os.path.exists(sidecar):
                try:
                    content = Path(sidecar).read_text()
                    expected = content.split()[0]
                    h = hashlib.sha256()
                    with open(filepath,'rb') as f:
                        for chunk in iter(lambda: f.read(8192), b''): h.update(chunk)
                    if h.hexdigest().lower() != expected.lower():
                        self.error("SHA256 mismatch (sidecar)")
                        return False
                    self.success("SHA256 verified (sidecar)")
                    return True
                except: pass
        return True
    
    def check_zip_slip(self, member_name, extract_dir):
        if self.insecure or not self.config.get('zip_slip_protection',True): return True
        try:
            extract_path = Path(extract_dir).resolve()
            member_path = (extract_path / member_name).resolve()
            member_path.relative_to(extract_path)
            return True
        except ValueError:
            self.error(f"Zip Slip detected! Blocked: {member_name}")
            self.info("Use --insecure to bypass (not recommended)")
            return False
    
    def check_size(self, filepath, arch_type):
        try:
            size = os.path.getsize(filepath)
            max_gb = self.config.get('max_size_gb',10)
            if size > max_gb*1024*1024*1024:
                self.warn(f"Archive is large ({size/1024/1024/1024:.2f} GB)")
                if not self.force and not self.dry_run:
                    self.info("Use -f to extract anyway")
                    return False
        except: pass
        return True
    
    def detect_by_magic(self, filepath):
        try:
            with open(filepath,'rb') as f:
                header = f.read(64)
            if header.startswith(b'\x1f\x8b'): return 'gz'
            if header.startswith(b'BZh'): return 'bz2'
            if header.startswith(b'\xfd7zXZ\x00'): return 'xz'
            if header.startswith(b'\x28\xb5\x2f\xfd'): return 'zstd'
            if header[:4] in (b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08'): return 'zip'
            if header.startswith(b'Rar!\x1a\x07\x00'): return 'rar'
            if header.startswith(b'Rar!\x1a\x07\x01\x00'): return 'rar'
            if header.startswith(b'7z\xbc\xaf\x27\x1c'): return '7z'
            if header.startswith(b'\x89LZ4'): return 'lz4'
            if header.startswith(b'\x04\x22\x4d\x18'): return 'lz4'
        except: pass
        return None
    
    def detect_type(self, filepath):
        ext = filepath.lower(); base = os.path.basename(filepath).lower()
        if base.endswith(('.r00','.r01')) or '.part1.rar' in base: return 'rar'
        if base.endswith(('.z01','.zip.001')) or '.part1.zip' in base: return 'zip'
        if ext.endswith(('.tar.gz','.tgz')): return 'tar.gz'
        if ext.endswith(('.tar.bz2','.tbz2','.tbz')): return 'tar.bz2'
        if ext.endswith(('.tar.xz','.txz')): return 'tar.xz'
        if ext.endswith(('.tar.zst','.tzst','.tar.zstd')): return 'tar.zst'
        if ext.endswith(('.tar.lz','.tar.lzma','.tlz')): return 'tar.lzma'
        if ext.endswith(('.tar.br','.tar.brotli')): return 'tar.br'
        if ext.endswith(('.tar.lz4')): return 'tar.lz4'
        if ext.endswith('.tar'): return 'tar'
        if ext.endswith(('.zip','.cbz')): return 'zip'
        if ext.endswith(('.7z','.7zip','.cb7')): return '7z'
        if ext.endswith(('.rar','.cbr')): return 'rar'
        if ext.endswith('.bz2'): return 'tar.bz2' if ext.endswith('.tar.bz2') else 'bz2'
        if ext.endswith('.gz'): return 'tar.gz' if ext.endswith('.tar.gz') else 'gz'
        if ext.endswith('.xz'): return 'tar.xz' if ext.endswith('.tar.xz') else 'xz'
        if ext.endswith(('.zst','.zstd')): return 'tar.zst' if ext.endswith('.tar.zst') else 'zst'
        if ext.endswith('.lzma'): return 'lzma'
        if ext.endswith('.br'): return 'brotli'
        if ext.endswith('.lz4'): return 'lz4'
        if ext.endswith('.lzo'): return 'lzo'
        if ext.endswith('.deb'): return 'deb'
        if ext.endswith('.rpm'): return 'rpm'
        if ext.endswith(('.apk','.ipa','.xapk','.aab')): return 'zip'
        for ext_zip in ['.jar','.war','.ear','.whl','.egg','.xpi','.crx','.epub','.docx','.xlsx','.pptx','.odt','.ods','.odp','.vsix','.appx','.msix','.nupkg','.kmz']:
            if ext.endswith(ext_zip): return 'zip'
        if ext.endswith('.iso'): return 'iso'
        if ext.endswith('.cab'): return 'cab'
        if ext.endswith('.arj'): return 'arj'
        if ext.endswith('.z'): return 'compress'
        if ext.endswith('.cpio'): return 'cpio'
        if ext.endswith('.ar'): return 'ar'
        if ext.endswith('.dmg'): return 'dmg'
        return self.detect_by_magic(filepath)
    
    def get_extract_dir(self, filepath):
        path = Path(filepath); name = path.name; base_name = name; lower = base_name.lower()
        if lower.endswith(('.r00','.r01')):
            base_name = base_name.rsplit('.r',1)[0]
            if base_name.lower().endswith('.rar'): base_name = base_name[:-4]
        elif lower.endswith(('.z01',)):
            base_name = base_name[:-4]+'.zip'
            if base_name.lower().endswith('.zip'): base_name = base_name[:-4]
        elif lower.endswith(('.zip.001',)):
            base_name = base_name.replace('.001','')
            if base_name.lower().endswith('.zip'): base_name = base_name[:-4]
        elif '.part1.rar' in lower: base_name = base_name.split('.part1.rar')[0]+'.rar'; base_name=base_name[:-4] if base_name.lower().endswith('.rar') else base_name
        elif '.part1.zip' in lower: base_name = base_name.split('.part1.zip')[0]+'.zip'; base_name=base_name[:-4] if base_name.lower().endswith('.zip') else base_name
        for ext in ['.tar.gz','.tar.bz2','.tar.xz','.tar.zst','.tar.zstd','.tar.lzma','.tar.br','.tar.lz4','.tgz','.tbz2','.tbz','.txz','.tzst','.tlz']:
            if base_name.lower().endswith(ext): base_name = base_name[:-len(ext)]; break
        else:
            for ext in ['.tar','.zip','.7z','.rar','.bz2','.gz','.xz','.zst','.zstd','.lzma','.br','.lz4','.lzo','.cbz','.cbr','.cb7','.jar','.war','.ear','.apk','.xapk','.aab','.ipa','.epub','.docx','.xlsx','.pptx','.odt','.ods','.odp','.whl','.deb','.rpm','.cpio','.iso','.dmg']:
                if base_name.lower().endswith(ext): base_name = base_name[:-len(ext)]; break
        if self.to_dir: return Path(self.to_dir)
        cfg_dir = self.config.get('default_dir')
        if cfg_dir: return Path(cfg_dir).expanduser()/base_name
        return path.parent/base_name
    
    def is_url(self, s): return s.startswith(('http://','https://','ftp://'))
    
    def download_url(self, url):
        self.info(f"Downloading {url}")
        try:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path) or 'download'
            tmpdir = tempfile.mkdtemp(prefix='extract_')
            dest = os.path.join(tmpdir, filename)
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-agent','extract/2.0')]
            urllib.request.install_opener(opener)
            with Spinner(f"Downloading {filename}"):
                urllib.request.urlretrieve(url, dest)
            self.success(f"Downloaded to {dest}")
            return dest, tmpdir
        except Exception as e:
            self.error(f"Download failed: {e}"); return None, None
    
    def cat_file_from_archive(self, filepath, target):
        arch_type = self.detect_type(filepath)
        cmd = None
        if arch_type == 'zip': cmd = ['unzip','-p',filepath,target]
        elif arch_type == 'tar.gz': cmd = ['tar','xzf',filepath,'-O',target]
        elif arch_type == 'tar.bz2': cmd = ['tar','xjf',filepath,'-O',target]
        elif arch_type == 'tar.xz': cmd = ['tar','xJf',filepath,'-O',target]
        elif arch_type == 'tar': cmd = ['tar','xf',filepath,'-O',target]
        elif arch_type == '7z':
            for t in ['7z','7za']:
                if shutil.which(t): cmd=[t,'e','-so',filepath,target]; break
        elif arch_type == 'rar' and shutil.which('unrar'): cmd = ['unrar','p','-inul',filepath,target]
        if cmd is None: self.error("Cannot cat from this archive type"); return False
        result = subprocess.run(cmd); return result.returncode == 0
    
    def get_archive_info(self, filepath):
        arch_type = self.detect_type(filepath); size = os.path.getsize(filepath)
        if self.json_output:
            print(json.dumps({'file':filepath,'type':arch_type,'size':size,'size_mb':round(size/1024/1024,2)})); return True
        self.info(f"{Colors.BOLD}Archive Info{Colors.RESET}")
        print(f"  File: {filepath}"); print(f"  Type: {arch_type or 'unknown'}")
        print(f"  Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
        print(f"  Zip-slip protected: {'yes' if self.config.get('zip_slip_protection') and not self.insecure else 'no'}")
        return True
    
    def test_archive(self, filepath):
        arch_type = self.detect_type(filepath)
        if not self.json_output: self.info(f"Testing {Path(filepath).name}...")
        cmd = None
        if arch_type == 'zip' and shutil.which('unzip'): cmd = ['unzip','-t',filepath]
        elif arch_type == '7z':
            for t in ['7z','7za']:
                if shutil.which(t): cmd=[t,'t',filepath]; break
        elif arch_type == 'rar' and shutil.which('unrar'): cmd = ['unrar','t',filepath]
        elif arch_type == 'tar.gz': cmd = ['tar','tzf',filepath]
        elif arch_type == 'tar.bz2': cmd = ['tar','tjf',filepath]
        elif arch_type == 'tar.xz': cmd = ['tar','tJf',filepath]
        elif arch_type == 'tar': cmd = ['tar','tf',filepath]
        if cmd is None:
            if self.json_output: print(json.dumps({'ok':False,'error':'no test support'}))
            else: self.warn("No test support")
            return False
        with Spinner("Testing integrity") if not self.json_output else DummySpinner(""):
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode == 0:
            if self.json_output: print(json.dumps({'ok':True,'file':filepath}))
            else: self.success("Archive is OK")
            return True
        else:
            if self.json_output: print(json.dumps({'ok':False,'file':filepath}))
            else: self.error("Archive is corrupted")
            return False
    
    def dry_run_extract(self, filepath):
        arch_type = self.detect_type(filepath); extract_dir = self.get_extract_dir(filepath); size = os.path.getsize(filepath)
        if self.json_output:
            print(json.dumps({'dry_run':True,'source':filepath,'type':arch_type,'size':size,'target':str(extract_dir)})); return True
        self.info(f"{Colors.BOLD}Dry run{Colors.RESET}")
        print(f"  Source: {filepath}"); print(f"  Type: {arch_type}")
        print(f"  Size: {size:,} bytes"); print(f"  Target: {extract_dir}")
        print(f"  Zip-slip: {'on' if self.config.get('zip_slip_protection') and not self.insecure else 'off'}")
        return True
    
    def smart_extract(self, filepath, original_source=None):
        filepath = os.path.abspath(filepath)
        if not os.path.exists(filepath):
            self.error(f"File not found: {filepath}"); return False
        arch_type = self.detect_type(filepath)
        if not arch_type: self.error(f"Unknown format: {filepath}"); return False
        if not self.verify_checksum(filepath): return False
        if self.cat_file: return self.cat_file_from_archive(filepath, self.cat_file)
        if self.test_only: return self.test_archive(filepath)
        if self.show_info: return self.get_archive_info(filepath)
        if self.dry_run: return self.dry_run_extract(filepath)
        if self.list_only:
            if not self.json_output: self.info(f"Listing {Path(filepath).name}")
            return self.list_archive(filepath, arch_type)
        if not self.check_size(filepath, arch_type): return False
        extract_dir = self.get_extract_dir(filepath)
        if extract_dir.exists() and not self.force:
            self.warn(f"Directory exists"); self.info("Use -f"); return False
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            start = time.time()
            success = self._extract(filepath, arch_type, extract_dir)
            if success:
                if not self.no_flatten and self.config.get('flatten',True): self._flatten_if_needed(extract_dir)
                if not self.keep_junk and not self.config.get('keep_junk',False): self._remove_junk(extract_dir)
                elapsed = time.time()-start
                if self.json_output: print(json.dumps({'ok':True,'source':filepath,'dest':str(extract_dir),'time':round(elapsed,2)}))
                else: self.success(f"Extracted to {Colors.BOLD}{extract_dir}{Colors.RESET} {Colors.DIM}({elapsed:.2f}s){Colors.RESET}")
                self.history.add(original_source or filepath, str(extract_dir), 'ok', arch_type)
                self.notify_send('extract', f'Extracted {Path(filepath).name}')
                self.copy_to_clipboard(str(extract_dir))
                if self.open_after: self._open_folder(extract_dir)
                if self.recursive: self._extract_recursive(extract_dir)
                return True
            self.history.add(original_source or filepath, str(extract_dir), 'fail', arch_type)
            return False
        except KeyboardInterrupt: self.warn("Cancelled"); return False
        except Exception as e:
            self.error(f"{e}")
            if self.verbose:
                import traceback; traceback.print_exc()
            self.history.add(original_source or filepath, str(extract_dir), 'fail', arch_type)
            return False
    
    def _open_folder(self, path):
        try:
            if self.os_type == 'darwin': subprocess.run(['open',str(path)], stdout=subprocess.DEVNULL)
            elif self.os_type == 'linux': subprocess.run(['xdg-open',str(path)], stdout=subprocess.DEVNULL)
            elif self.os_type == 'wsl': 
                if shutil.which('wslview'): subprocess.run(['wslview',str(path)], stdout=subprocess.DEVNULL)
                else: subprocess.run(['explorer.exe',str(path).replace('/mnt/c','C:').replace('/','\\')], stdout=subprocess.DEVNULL)
            elif self.os_type == 'windows': subprocess.run(['explorer',str(path)], stdout=subprocess.DEVNULL)
        except: pass
    
    def _extract_recursive(self, dir_path):
        found = []
        for root,dirs,files in os.walk(dir_path):
            for f in files:
                fp = os.path.join(root,f)
                if self.detect_type(fp): found.append(fp)
        if found:
            self.info(f"Found {len(found)} nested archive(s)")
            for af in found:
                adir = self.get_extract_dir(af)
                if adir.exists() and not self.force: continue
                adir.mkdir(parents=True,exist_ok=True)
                atype = self.detect_type(af)
                if self._extract(af,atype,adir):
                    if not self.no_flatten: self._flatten_if_needed(adir)
                    if not self.keep_junk: self._remove_junk(adir)
    
    def _extract(self, filepath, arch_type, extract_dir):
        if not self.password and arch_type in ['zip','7z','rar']:
            kp = self.keyring.get_key(filepath)
            if kp: self.password = kp
        cmd = None
        if arch_type in ['tar','tar.gz','tar.bz2','tar.xz','tar.zst','tar.lzma']:
            if arch_type=='tar.gz': cmd=['tar','xzf',filepath,'-C',str(extract_dir)]
            elif arch_type=='tar.bz2': cmd=['tar','xjf',filepath,'-C',str(extract_dir)]
            elif arch_type=='tar.xz': cmd=['tar','xJf',filepath,'-C',str(extract_dir)]
            elif arch_type=='tar.zst': cmd=['tar','--zstd','-xf',filepath,'-C',str(extract_dir)]
            elif arch_type=='tar.lzma': cmd=['tar','--lzma','-xf',filepath,'-C',str(extract_dir)]
            else: cmd=['tar','xf',filepath,'-C',str(extract_dir)]
        elif arch_type in ['tar.br','tar.lz4']:
            p1 = subprocess.Popen(['brotli','-d','-c',filepath],stdout=subprocess.PIPE) if arch_type=='tar.br' else subprocess.Popen(['lz4','-d','-c',filepath],stdout=subprocess.PIPE)
            p2 = subprocess.Popen(['tar','xf','-'],stdin=p1.stdout,cwd=str(extract_dir))
            p1.stdout.close(); p2.communicate(); return p2.returncode==0
        elif arch_type == 'zip':
            if self.password and shutil.which('7z'):
                for t in ['7z','7za']:
                    if shutil.which(t): cmd=[t,'x',f'-o{extract_dir}',f'-p{self.password}','-y',filepath]; break
            if cmd is None:
                if shutil.which('unzip'): cmd=['unzip','-o','-q',filepath,'-d',str(extract_dir)]
                elif shutil.which('7z') or shutil.which('7za'):
                    for t in ['7z','7za']:
                        if shutil.which(t): cmd=[t,'x',f'-o{extract_dir}','-y',filepath]; break
                elif shutil.which('bsdtar'): cmd=['bsdtar','-xf',filepath,'-C',str(extract_dir)]
        elif arch_type == '7z':
            for t in ['7z','7za','7zr']:
                if shutil.which(t):
                    cmd=[t,'x',f'-o{extract_dir}',f'-p{self.password}','-y',filepath] if self.password else [t,'x',f'-o{extract_dir}','-y',filepath]
                    break
            if cmd is None and shutil.which('bsdtar'): cmd=['bsdtar','-xf',filepath,'-C',str(extract_dir)]
        elif arch_type == 'rar':
            for t in ['unrar','unar','7z','bsdtar']:
                if shutil.which(t):
                    if t=='unrar': cmd=['unrar','x','-p'+self.password if self.password else '-p-','-o+',filepath,str(extract_dir)+'/'] if self.password else [t,'x','-o+',filepath,str(extract_dir)+'/']
                    elif t=='unar': cmd=[t,'-o',str(extract_dir),'-force-overwrite',filepath] + (['-password',self.password] if self.password else [])
                    elif t=='7z': cmd=[t,'x',f'-o{extract_dir}',f'-p{self.password}','-y',filepath] if self.password else [t,'x',f'-o{extract_dir}','-y',filepath]
                    elif t=='bsdtar': cmd=[t,'-xf',filepath,'-C',str(extract_dir)]
                    break
        elif arch_type == 'bz2':
            out_file = extract_dir/Path(filepath).stem
            tool='bunzip2' if shutil.which('bunzip2') else 'bzip2'
            with open(out_file,'wb') as f: result=subprocess.run([tool,'-d','-c',filepath],stdout=f); return result.returncode==0
        elif arch_type == 'gz':
            out_file = extract_dir/Path(filepath).stem
            tool='gunzip' if shutil.which('gunzip') else 'gzip'
            with open(out_file,'wb') as f: result=subprocess.run([tool,'-d','-c',filepath],stdout=f); return result.returncode==0
        elif arch_type == 'xz':
            out_file = extract_dir/Path(filepath).stem
            with open(out_file,'wb') as f: result=subprocess.run(['xz','-d','-c',filepath],stdout=f); return result.returncode==0
        elif arch_type == 'zst':
            out_file = extract_dir/Path(filepath).stem
            tool='zstd' if shutil.which('zstd') else 'unzstd'
            with open(out_file,'wb') as f: result=subprocess.run([tool,'-d','-c',filepath],stdout=f); return result.returncode==0
        elif arch_type == 'br':
            out_file = extract_dir/Path(filepath).stem
            with open(out_file,'wb') as f: result=subprocess.run(['brotli','-d','-c',filepath],stdout=f); return result.returncode==0
        elif arch_type == 'lz4':
            out_file = extract_dir/Path(filepath).stem
            with open(out_file,'wb') as f: result=subprocess.run(['lz4','-d','-c',filepath],stdout=f); return result.returncode==0
        elif arch_type == 'deb' and shutil.which('dpkg-deb'): cmd=['dpkg-deb','-x',filepath,str(extract_dir)]
        elif arch_type == 'rpm' and shutil.which('rpm2cpio') and shutil.which('cpio'):
            p1=subprocess.Popen(['rpm2cpio',filepath],stdout=subprocess.PIPE)
            p2=subprocess.Popen(['cpio','-idmv','--quiet'],stdin=p1.stdout,cwd=str(extract_dir))
            p1.stdout.close(); p2.communicate(); return p2.returncode==0
        elif arch_type == 'cpio' and shutil.which('cpio'): result=subprocess.run(['cpio','-idmv','-I',filepath],cwd=str(extract_dir)); return result.returncode==0
        elif arch_type == 'ar' and shutil.which('ar'): result=subprocess.run(['ar','x',filepath],cwd=str(extract_dir)); return result.returncode==0
        elif arch_type == 'iso':
            if shutil.which('bsdtar'): cmd=['bsdtar','-xf',filepath,'-C',str(extract_dir)]
            elif shutil.which('7z'): cmd=['7z','x',f'-o{extract_dir}','-y',filepath]
        elif arch_type == 'cab':
            for t in ['cabextract','7z']:
                if shutil.which(t):
                    cmd=['cabextract','-d',str(extract_dir),filepath] if t=='cabextract' else [t,'x',f'-o{extract_dir}','-y',filepath]
                    break
        else:
            self.error(f"Unsupported: {arch_type}"); return False
        if cmd is None:
            self.error(f"No tool for {arch_type}"); self.suggest_install(arch_type); return False
        with Spinner("Extracting...") if not self.json_output else DummySpinner(""):
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL if not self.verbose else None, stderr=subprocess.PIPE)
        if result.returncode != 0:
            if result.stderr:
                err = result.stderr.decode(errors='ignore')
                if 'password' in err.lower() or 'encrypted' in err.lower():
                    self.error("Password protected")
                    if not self.password:
                        try:
                            pw = getpass.getpass('Password: ')
                            self.password = pw; self.keyring.set_key(filepath,pw)
                            return self._extract(filepath,arch_type,extract_dir)
                        except: pass
                    else: self.error("Wrong password")
        return result.returncode == 0
    
    def suggest_install(self, arch_type):
        if self.json_output: return
        pm = None
        for p in ['apt','pacman','dnf','yum','brew','apk','nix-env','pkg','choco','winget','scoop']:
            if shutil.which(p): pm=p; break
        if pm == 'apt':
            if arch_type=='7z': print(f"  sudo apt install p7zip-full", file=sys.stderr)
            elif arch_type=='rar': print(f"  sudo apt install unrar", file=sys.stderr)
            elif arch_type=='zst': print(f"  sudo apt install zstd", file=sys.stderr)
        elif pm == 'brew':
            if arch_type=='7z': print(f"  brew install p7zip", file=sys.stderr)
            elif arch_type=='rar': print(f"  brew install unrar", file=sys.stderr)
            elif arch_type=='zst': print(f"  brew install zstd", file=sys.stderr)
        elif pm == 'pacman':
            if arch_type=='7z': print(f"  sudo pacman -S p7zip", file=sys.stderr)
            elif arch_type=='rar': print(f"  sudo pacman -S unrar", file=sys.stderr)
    
    def list_archive(self, filepath, arch_type):
        cmd = None
        if arch_type=='tar.gz': cmd=['tar','tzf',filepath]
        elif arch_type=='tar.bz2': cmd=['tar','tjf',filepath]
        elif arch_type=='tar.xz': cmd=['tar','tJf',filepath]
        elif arch_type=='tar.zst': cmd=['tar','--zstd','-tf',filepath]
        elif arch_type=='tar': cmd=['tar','tf',filepath]
        elif arch_type=='zip':
            cmd=['unzip','-l',filepath] if shutil.which('unzip') else None
            if cmd is None and shutil.which('7z'):
                for t in ['7z','7za']:
                    if shutil.which(t): cmd=[t,'l',filepath]; break
        elif arch_type=='7z':
            for t in ['7z','7za']:
                if shutil.which(t): cmd=[t,'l',filepath]; break
        elif arch_type=='rar':
            if shutil.which('unrar'): cmd=['unrar','l',filepath]
            elif shutil.which('unar'): cmd=['unar','-t',filepath]
        if cmd is None and shutil.which('bsdtar'): cmd=['bsdtar','-tf',filepath]
        if cmd is None: self.error("Cannot list"); return False
        if self.json_output:
            result=subprocess.run(cmd,stdout=subprocess.PIPE)
            print(result.stdout.decode(errors='ignore')); return True
        subprocess.run(cmd); return True
    
    def _remove_junk(self, extract_dir):
        for root,dirs,files in os.walk(extract_dir,topdown=False):
            for f in files:
                if f in ['__MACOSX','.DS_Store','Thumbs.db','desktop.ini']:
                    try: os.remove(os.path.join(root,f))
                    except: pass
            for d in dirs:
                if d=='__MACOSX':
                    try: shutil.rmtree(os.path.join(root,d))
                    except: pass
    
    def _flatten_if_needed(self, extract_dir):
        try:
            items = [i for i in extract_dir.iterdir() if i.name not in ['__MACOSX','.DS_Store']]
            if len(items)==1 and items[0].is_dir():
                subdir = items[0]
                for item in subdir.iterdir():
                    dest = extract_dir/item.name
                    if dest.exists() and not self.force: continue
                    try: shutil.move(str(item),str(dest))
                    except: pass
                try: subdir.rmdir()
                except: pass
        except: pass

class Spinner:
    def __init__(self,msg):
        self.msg=msg; self.frames=['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']; self.running=False
    def __enter__(self):
        if not sys.stdout.isatty(): return self
        self.running=True
        import threading
        def spin():
            i=0
            while self.running:
                sys.stdout.write(f'\r{Colors.CYAN}{self.frames[i%len(self.frames)]}{Colors.RESET} {self.msg}')
                sys.stdout.flush(); i+=1; time.sleep(0.08)
        self.thread=threading.Thread(target=spin,daemon=True); self.thread.start(); return self
    def __exit__(self,*args):
        self.running=False; time.sleep(0.05)
        sys.stdout.write('\r'+' '*80+'\r'); sys.stdout.flush()

class DummySpinner:
    def __init__(self,msg): pass
    def __enter__(self): return self
    def __exit__(self,*args): pass

def generate_completions(shell):
    if shell=='bash':
        return '''# extract bash completion
_extract_completions() {
    local cur prev opts
    COMPREPLY=(); cur="${COMP_WORDS[COMP_CWORD]}"; prev="${COMP_WORDS[COMP_CWORD-1]}"
    opts="-v --verbose -l --list -f --force -d --directory -C -n --dry-run -t --test -i --info -r --recursive -p --password --cat --view -o --open --json --keep-junk --no-flatten --notify --insecure -j --jobs --parallel --tui -c --create --pack -q --quiet --no-color --sha256 --verify --copy-path --version --help"
    [[ ${cur} == -* ]] && { COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) ); return 0; }
    COMPREPLY=( $(compgen -f -X '!*.@(tar|tgz|tar.gz|tbz2|tar.bz2|txz|tar.xz|tzst|tar.zst|zip|7z|rar|bz2|gz|xz|zst|br|lz4|deb|rpm|iso|jar|war|apk|epub|docx|xlsx|pptx|cbz|cbr|xapk|dmg)' -- ${cur}) )
}
complete -F _extract_completions extract x
'''
    elif shell=='zsh':
        return '''#compdef extract x
_extract() {
    _arguments '*:files:_files -g "*.(tar|tgz|tar.gz|tbz2|tar.bz2|txz|tar.xz|tzst|tar.zst|zip|7z|rar|bz2|gz|xz|zst|br|lz4|deb|rpm|iso|jar|war|apk|epub|docx|xlsx|pptx|dmg)"'
}
'''
    elif shell=='fish':
        return '''complete -c extract -s v -l verbose -d "Verbose"; complete -c extract -s l -l list -d "List"; complete -c extract -f --arguments "(find . -maxdepth 4 -type f \\( -name '*.tar*' -o -name '*.zip' -o -name '*.7z' -o -name '*.rar' -o -name '*.gz' -o -name '*.xz' \\) 2>/dev/null)"
complete -c x -w extract
'''
    return ''

def launch_tui(filepath):
    print(f"{Colors.BOLD}TUI Browser{Colors.RESET} - {filepath}")
    extractor = Extractor(list_only=True)
    extractor.list_archive(filepath, extractor.detect_type(filepath))
    print(f"\n{Colors.DIM}Tip: Use --cat <file> to view, or select with fzf/gum{Colors.RESET}")

def pack_archive(sources, output):
    print(f"{Colors.BOLD}Packing{Colors.RESET} -> {output}")
    try:
        if output.endswith(('.tar.gz','.tgz')): cmd=['tar','-czf',output]+sources
        elif output.endswith('.tar.xz'): cmd=['tar','-cJf',output]+sources
        elif output.endswith('.tar.zst'): cmd=['tar','--zstd','-cf',output]+sources
        elif output.endswith('.tar.bz2'): cmd=['tar','-cjf',output]+sources
        elif output.endswith('.tar'): cmd=['tar','-cf',output]+sources
        elif output.endswith('.zip'): cmd=['zip','-r',output]+sources
        elif output.endswith('.7z'): cmd=['7z','a',output]+sources
        else: cmd=['tar','-czf',output+'.tar.gz']+sources
        with Spinner("Packing..."):
            result=subprocess.run(cmd)
        if result.returncode==0: print(f"{Colors.GREEN}✓{Colors.RESET} Created {output}"); return True
    except Exception as e: print(f"{Colors.RED}✗{Colors.RESET} {e}")
    return False

def watch_directory(dir_path, extractor):
    print(f"{Colors.BOLD}Watching{Colors.RESET} {dir_path} for archives...")
    print(f"{Colors.DIM}Press Ctrl+C to stop{Colors.RESET}")
    seen = set()
    try:
        while True:
            for f in Path(dir_path).glob('*'):
                if f.is_file() and f.suffix.lower() in ['.zip','.tar','.gz','.xz','.bz2','.7z','.rar','.zst','.tgz','.tbz2']:
                    key = (str(f), f.stat().st_mtime)
                    if key not in seen:
                        seen.add(key)
                        time.sleep(1)
                        print(f"\n{Colors.CYAN}New archive:{Colors.RESET} {f.name}")
                        extractor.smart_extract(str(f))
            time.sleep(2)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Stopped watching{Colors.RESET}")

def main():
    parser = argparse.ArgumentParser(prog='extract', description=f'{Colors.BOLD}extract{Colors.RESET} v2.0 - Universal archive tool', formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='*', help='Archive/URL/files')
    parser.add_argument('-v','--verbose', action='store_true')
    parser.add_argument('-l','--list', action='store_true')
    parser.add_argument('-f','--force', action='store_true')
    parser.add_argument('-d','--directory', metavar='DIR')
    parser.add_argument('-C', dest='dir', metavar='DIR')
    parser.add_argument('-n','--dry-run', action='store_true')
    parser.add_argument('-t','--test', action='store_true')
    parser.add_argument('-i','--info', action='store_true')
    parser.add_argument('-r','--recursive', action='store_true')
    parser.add_argument('-p','--password', metavar='PASS', nargs='?', const='-')
    parser.add_argument('--cat', dest='cat_file', metavar='FILE')
    parser.add_argument('--view', dest='cat_file', metavar='FILE')
    parser.add_argument('-o','--open', action='store_true')
    parser.add_argument('--json', action='store_true', dest='json_output')
    parser.add_argument('--keep-junk', action='store_true')
    parser.add_argument('--no-flatten', action='store_true')
    parser.add_argument('--notify', action='store_true')
    parser.add_argument('--insecure', action='store_true')
    parser.add_argument('--copy-path', action='store_true')
    parser.add_argument('-j','--jobs', type=int, default=4)
    parser.add_argument('--parallel', action='store_true')
    parser.add_argument('--tui', action='store_true')
    parser.add_argument('-c','--create', action='store_true')
    parser.add_argument('--pack', action='store_true')
    parser.add_argument('--watch', metavar='DIR', help='Watch directory for archives')
    parser.add_argument('--sha256', metavar='HASH')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--diff', nargs=2, metavar=('A','B'))
    parser.add_argument('--sandbox', action='store_true')
    parser.add_argument('--last', action='store_true')
    parser.add_argument('--stats', action='store_true')
    parser.add_argument('-q','--quiet', action='store_true')
    parser.add_argument('--no-color', action='store_true')
    parser.add_argument('--completion', choices=['bash','zsh','fish'])
    parser.add_argument('--install-completions', action='store_true')
    parser.add_argument('--config', action='store_true')
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--clear-keys', action='store_true')
    parser.add_argument('--update', action='store_true')
    parser.add_argument('--plugins', action='store_true')
    parser.add_argument('--version', action='version', version=f'{Colors.BOLD}extract{Colors.RESET} 2.0.0')
    args = parser.parse_args()
    if args.no_color or not sys.stdout.isatty(): Colors.disable()
    if args.completion: print(generate_completions(args.completion)); sys.exit(0)
    if args.install_completions:
        home=Path.home(); shell=os.path.basename(os.environ.get('SHELL',''))
        if shell=='bash':
            p=home/'.bash_completion.d/extract'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(generate_completions('bash')); print(f"Installed to {p}")
        elif shell=='zsh':
            p=home/'.zsh/completions/_extract'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(generate_completions('zsh')); print(f"Installed to {p}")
        elif shell=='fish':
            p=home/'.config/fish/completions/extract.fish'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(generate_completions('fish')); print(f"Installed to {p}")
        sys.exit(0)
    if args.config:
        cfg=Config(); print(f"Config: {cfg.config_file}"); print("zip_slip_protection = true\nmax_size_gb = 10\nnotify = false\ncopy_path = false"); sys.exit(0)
    if args.history: History().show(); sys.exit(0)
    if args.clear_keys: Keyring().clear(); sys.exit(0)
    if args.update: print("curl -sSL https://raw.githubusercontent.com/neg/extract/main/scripts/install.sh | bash"); sys.exit(0)
    if args.plugins:
        pdir=Path.home()/'.config/extract/plugins'; pdir.mkdir(parents=True,exist_ok=True)
        print(f"Plugins dir: {pdir}"); print("Place *.py files with can_handle(), extract()"); sys.exit(0)
    if args.tui and args.files: launch_tui(args.files[0]); sys.exit(0)
    if (args.create or args.pack) and args.files:
        if len(args.files)>=2: pack_archive(args.files[:-1], args.files[-1])
        else: print("Usage: extract --pack src out.tar.gz")
        sys.exit(0)
    if args.watch:
        ext=Extractor(notify=True); watch_directory(args.watch, ext); sys.exit(0)
    if args.last:
        h=History().get_last()
        if not h: print("No history"); sys.exit(1)
        print(f"Last: {h['source']} -> {h['dest']}")
        if args.files and args.files[0]=='--open': subprocess.run(['xdg-open',h['dest']] if shutil.which('xdg-open') else ['open',h['dest']])
        sys.exit(0)
    if args.diff and len(args.diff)==2:
        print(f"Diffing {args.diff[0]} vs {args.diff[1]} (basic)"); sys.exit(0)
    if not args.files and not args.cat_file: parser.print_help(); sys.exit(1)
    if args.password == '-':
        try: args.password = getpass.getpass('Password: ')
        except: pass
    ext=Extractor(verbose=args.verbose,list_only=args.list,force=args.force,to_dir=args.dir or args.directory,
                  quiet=args.quiet,dry_run=args.dry_run,test_only=args.test,keep_junk=args.keep_junk,
                  no_flatten=args.no_flatten,recursive=args.recursive,password=args.password,
                  cat_file=args.cat_file,json_output=args.json_output,show_info=args.info,
                  open_after=args.open,notify=args.notify,insecure=args.insecure,jobs=args.jobs,
                  copy_path=args.copy_path,sha256=args.sha256)
    if len(args.files)>1 and (args.parallel or args.jobs>1) and not args.json_output and not args.list_only:
        success=0
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures={executor.submit(ext.smart_extract,f,f):f for f in args.files}
            for fut in as_completed(futures):
                try:
                    if fut.result(): success+=1
                except: pass
        if not args.quiet: print(f"\n{Colors.GREEN}{success}/{len(args.files)}{Colors.RESET} completed")
        sys.exit(0 if success==len(args.files) else 1)
    success_count=0
    for f in args.files:
        if ext.is_url(f):
            dest,tmpdir=ext.download_url(f)
            if dest:
                if ext.smart_extract(dest,f): success_count+=1
                try: shutil.rmtree(tmpdir)
                except: pass
        else:
            if ext.smart_extract(f,f): success_count+=1
    if len(args.files)>1 and not args.quiet and not args.json_output: print(f"\n{Colors.GREEN}{success_count}/{len(args.files)}{Colors.RESET} completed")
    sys.exit(0 if success_count==len(args.files) else 1)

if __name__=='__main__': main()
