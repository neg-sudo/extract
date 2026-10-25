#!/usr/bin/env python3
# extract - Universal archive extractor for all platforms
# Copyright (c) 2026 extract contributors
# Licensed under MIT License

import os
import sys
import shutil
import argparse
import subprocess
import platform
from pathlib import Path

class Extractor:
    def __init__(self, verbose=False, list_only=False, force=False, to_dir=None):
        self.verbose = verbose
        self.list_only = list_only
        self.force = force
        self.to_dir = to_dir
        self.os_type = platform.system().lower()
        if self.os_type == 'linux':
            try:
                with open('/proc/version', 'r') as f:
                    if 'microsoft' in f.read().lower():
                        self.os_type = 'wsl'
            except:
                pass
    
    def log(self, msg):
        if self.verbose:
            print(f"[extract] {msg}", file=sys.stderr)
    
    def detect_by_magic(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                header = f.read(32)
            if header.startswith(b'\x1f\x8b'): return 'gz'
            if header.startswith(b'BZh'): return 'bz2'
            if header.startswith(b'\xfd7zXZ\x00'): return 'xz'
            if header.startswith(b'\x28\xb5\x2f\xfd'): return 'zstd'
            if header.startswith(b'PK\x03\x04'): return 'zip'
            if header.startswith(b'PK\x05\x06'): return 'zip'
            if header.startswith(b'PK\x07\x08'): return 'zip'
            if header.startswith(b'Rar!\x1a\x07\x00'): return 'rar'
            if header.startswith(b'Rar!\x1a\x07\x01\x00'): return 'rar'
            if header.startswith(b'7z\xbc\xaf\x27\x1c'): return '7z'
            if header.startswith(b'\x89LZ4'): return 'lz4'
            if header.startswith(b'\x04\x22\x4d\x18'): return 'lz4'
            if header.startswith(b'\x1f\x9d'): return 'compress'
            if header.startswith(b'\x1f\xa0'): return 'compress'
        except:
            pass
        return None
    
    def detect_type(self, filepath):
        ext = filepath.lower()
        if ext.endswith(('.tar.gz', '.tgz')): return 'tar.gz'
        if ext.endswith(('.tar.bz2', '.tbz2', '.tbz')): return 'tar.bz2'
        if ext.endswith(('.tar.xz', '.txz')): return 'tar.xz'
        if ext.endswith(('.tar.zst', '.tzst')): return 'tar.zst'
        if ext.endswith(('.tar.lz', '.tar.lzma')): return 'tar.lzma'
        if ext.endswith('.tar'): return 'tar'
        if ext.endswith('.zip'): return 'zip'
        if ext.endswith(('.7z', '.7zip')): return '7z'
        if ext.endswith(('.rar', '.r00')): return 'rar'
        if ext.endswith(('.bz2')): 
            if ext.endswith('.tar.bz2'): return 'tar.bz2'
            return 'bz2'
        if ext.endswith(('.gz')): 
            if ext.endswith('.tar.gz'): return 'tar.gz'
            return 'gz'
        if ext.endswith(('.xz')): 
            if ext.endswith('.tar.xz'): return 'tar.xz'
            return 'xz'
        if ext.endswith(('.zst')): 
            if ext.endswith('.tar.zst'): return 'tar.zst'
            return 'zst'
        if ext.endswith('.lzma'): return 'lzma'
        if ext.endswith(('.deb')): return 'deb'
        if ext.endswith(('.rpm')): return 'rpm'
        if ext.endswith(('.iso')): return 'iso'
        if ext.endswith(('.cab')): return 'cab'
        if ext.endswith(('.arj')): return 'arj'
        if ext.endswith(('.ace')): return 'ace'
        if ext.endswith(('.z')): return 'compress'
        if ext.endswith(('.cpio')): return 'cpio'
        for ext_zip in ['.jar', '.war', '.apk', '.whl', '.xpi', '.crx', '.epub', 
                        '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.vsix']:
            if ext.endswith(ext_zip): return 'zip'
        if ext.endswith(('.br')): return 'brotli'
        if ext.endswith(('.zstd')): return 'zstd'
        if ext.endswith(('.lz4')): return 'lz4'
        if ext.endswith(('.sz')): return 'snappy'
        return self.detect_by_magic(filepath)
    
    def get_extract_dir(self, filepath):
        path = Path(filepath)
        name = path.name
        base_name = name
        for ext in ['.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst', '.tar.lzma', 
                   '.tgz', '.tbz2', '.tbz', '.txz', '.tzst']:
            if base_name.lower().endswith(ext):
                base_name = base_name[:-len(ext)]
                break
        else:
            for ext in ['.tar', '.zip', '.7z', '.rar', '.bz2', '.gz', '.xz', 
                       '.zst', '.lzma', '.br', '.zstd', '.lz4']:
                if base_name.lower().endswith(ext):
                    base_name = base_name[:-len(ext)]
                    break
        if self.to_dir:
            return Path(self.to_dir)
        return path.parent / base_name
    
    def smart_extract(self, filepath):
        filepath = os.path.abspath(filepath)
        if not os.path.exists(filepath):
            print(f"Error: {filepath} not found", file=sys.stderr)
            return False
        arch_type = self.detect_type(filepath)
        if not arch_type:
            print(f"Error: Unknown archive format for {filepath}", file=sys.stderr)
            print("Try: extract -l to inspect, or check file type with 'file'", file=sys.stderr)
            return False
        extract_dir = self.get_extract_dir(filepath)
        if self.list_only:
            return self.list_archive(filepath, arch_type)
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            success = self._extract(filepath, arch_type, extract_dir)
            if success:
                self._flatten_if_needed(extract_dir)
                print(f"✓ Extracted to {extract_dir}")
            return success
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return False
    
    def _extract(self, filepath, arch_type, extract_dir):
        cmd = None
        if arch_type == 'tar':
            cmd = ['tar', 'xf', filepath, '-C', str(extract_dir)]
        elif arch_type == 'tar.gz':
            cmd = ['tar', 'xzf', filepath, '-C', str(extract_dir)]
        elif arch_type == 'tar.bz2':
            cmd = ['tar', 'xjf', filepath, '-C', str(extract_dir)]
        elif arch_type == 'tar.xz':
            cmd = ['tar', 'xJf', filepath, '-C', str(extract_dir)]
        elif arch_type == 'tar.zst':
            cmd = ['tar', '--zstd', '-xf', filepath, '-C', str(extract_dir)]
        elif arch_type == 'tar.lzma':
            cmd = ['tar', '--lzma', '-xf', filepath, '-C', str(extract_dir)]
        elif arch_type == 'zip':
            cmd = ['unzip', '-o', '-q', filepath, '-d', str(extract_dir)]
        elif arch_type == '7z':
            for tool in ['7z', '7za', '7zr']:
                if shutil.which(tool):
                    cmd = [tool, 'x', f'-o{extract_dir}', '-y', filepath]
                    break
        elif arch_type == 'rar':
            for tool in ['unrar', 'unar']:
                if shutil.which(tool):
                    if tool == 'unrar':
                        cmd = [tool, 'x', '-o+', filepath, str(extract_dir) + '/']
                    else:
                        cmd = [tool, '-o', str(extract_dir), '-force-overwrite', filepath]
                    break
        elif arch_type == 'bz2':
            out_file = extract_dir / Path(filepath).stem
            with open(out_file, 'wb') as f:
                subprocess.run(['bunzip2', '-c', filepath], stdout=f)
            return True
        elif arch_type == 'gz':
            out_file = extract_dir / Path(filepath).stem
            with open(out_file, 'wb') as f:
                subprocess.run(['gunzip', '-c', filepath], stdout=f)
            return True
        elif arch_type == 'xz':
            out_file = extract_dir / Path(filepath).stem
            with open(out_file, 'wb') as f:
                subprocess.run(['xz', '-d', '-c', filepath], stdout=f)
            return True
        elif arch_type == 'zst':
            out_file = extract_dir / Path(filepath).stem
            with open(out_file, 'wb') as f:
                subprocess.run(['zstd', '-d', '-c', filepath], stdout=f)
            return True
        elif arch_type == 'br':
            out_file = extract_dir / Path(filepath).stem
            with open(out_file, 'wb') as f:
                subprocess.run(['brotli', '-d', '-c', filepath], stdout=f)
            return True
        elif arch_type == 'deb':
            cmd = ['dpkg-deb', '-x', filepath, str(extract_dir)]
        elif arch_type == 'rpm':
            p1 = subprocess.Popen(['rpm2cpio', filepath], stdout=subprocess.PIPE)
            p2 = subprocess.Popen(['cpio', '-idmv'], stdin=p1.stdout, cwd=str(extract_dir))
            p1.stdout.close()
            p2.communicate()
            return p2.returncode == 0
        elif arch_type == 'cpio':
            subprocess.run(['cpio', '-idmv', '-I', filepath], cwd=str(extract_dir))
            return True
        else:
            print(f"Unsupported format: {arch_type}", file=sys.stderr)
            return False
        if cmd is None:
            print(f"No tool available for {arch_type}", file=sys.stderr)
            return False
        self.log(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd)
        return result.returncode == 0
    
    def list_archive(self, filepath, arch_type):
        cmd = None
        if arch_type in ['tar', 'tar.gz', 'tar.bz2', 'tar.xz', 'tar.zst', 'tar.lzma']:
            if arch_type == 'tar.gz': cmd = ['tar', 'tzf', filepath]
            elif arch_type == 'tar.bz2': cmd = ['tar', 'tjf', filepath]
            elif arch_type == 'tar.xz': cmd = ['tar', 'tJf', filepath]
            elif arch_type == 'tar.zst': cmd = ['tar', '--zstd', '-tf', filepath]
            else: cmd = ['tar', 'tf', filepath]
        elif arch_type == 'zip':
            cmd = ['unzip', '-l', filepath]
        elif arch_type == '7z':
            for tool in ['7z', '7za', '7zr']:
                if shutil.which(tool):
                    cmd = [tool, 'l', filepath]
                    break
        elif arch_type == 'rar':
            for tool in ['unrar', 'unar']:
                if shutil.which(tool):
                    if tool == 'unrar':
                        cmd = [tool, 'l', filepath]
                    else:
                        cmd = [tool, '-t', filepath]
                    break
        if cmd is None:
            print("Cannot list this format or missing tools", file=sys.stderr)
            return False
        subprocess.run(cmd)
        return True
    
    def _flatten_if_needed(self, extract_dir):
        try:
            items = [i for i in extract_dir.iterdir() if not i.name.startswith('__MACOSX')]
            if len(items) == 1 and items[0].is_dir():
                subdir = items[0]
                for item in subdir.iterdir():
                    dest = extract_dir / item.name
                    if dest.exists() and not self.force:
                        continue
                    shutil.move(str(item), str(dest))
                try:
                    subdir.rmdir()
                except:
                    pass
        except:
            pass

def main():
    parser = argparse.ArgumentParser(
        description='Universal archive extractor for Linux, macOS, and Windows',
        epilog='Supports: tar, tar.gz/tgz, tar.bz2/tbz2, tar.xz/txz, tar.zst, zip, 7z, rar, bz2, gz, xz, zst, deb, rpm, and more. MIT Licensed.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('files', nargs='+', help='Archive files to extract')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-l', '--list', action='store_true', help='List contents without extracting')
    parser.add_argument('-f', '--force', action='store_true', help='Overwrite existing files')
    parser.add_argument('-d', '--directory', help='Extract to specific directory')
    parser.add_argument('-C', dest='dir', help='Change to directory')
    parser.add_argument('--version', action='version', version='extract 1.0.0')
    args = parser.parse_args()
    extractor = Extractor(verbose=args.verbose, list_only=args.list, 
                         force=args.force, to_dir=args.dir or args.directory)
    all_ok = all(extractor.smart_extract(f) for f in args.files)
    sys.exit(0 if all_ok else 1)

if __name__ == '__main__':
    main()
