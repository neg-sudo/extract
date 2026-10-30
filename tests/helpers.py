import io
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "lib" / "extract.py"
SAFEOPS = ROOT / "lib"


def run(args, cwd=None, home=None, timeout=120, input_text=None, extra_env=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SAFEOPS) + os.pathsep + env.get("PYTHONPATH", "")
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    if home:
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        env["APPDATA"] = str(Path(home) / "AppData" / "Roaming")
        env["LOCALAPPDATA"] = str(Path(home) / "AppData" / "Local")
        env["XDG_CONFIG_HOME"] = str(Path(home) / ".config")
        env["XDG_STATE_HOME"] = str(Path(home) / ".local" / "state")
        env["XDG_DATA_HOME"] = str(Path(home) / ".local" / "share")
    return subprocess.run(
        [sys.executable, str(EXTRACT)] + [str(a) for a in args],
        cwd=str(cwd) if cwd else None, env=env, timeout=timeout,
        input=input_text, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def make_zip(path, entries, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", compression) as zf:
        for name, data in entries.items():
            if isinstance(data, str):
                data = data.encode()
            zf.writestr(name, data)
    return path


def make_tar(path, entries, mode="w"):
    with tarfile.open(path, mode) as tf:
        for name, data in entries.items():
            if isinstance(data, str):
                data = data.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return path


def add_tar_member(path, info, data=b"", mode="a"):
    with tarfile.open(path, mode) as tf:
        tf.addfile(info, io.BytesIO(data) if data else None)


def make_symlink_tar(path, name, target):
    with tarfile.open(path, "w") as tf:
        info = tarfile.TarInfo(name)
        info.type = tarfile.SYMTYPE
        info.linkname = target
        tf.addfile(info)


def make_hardlink_tar(path, name, target):
    with tarfile.open(path, "w") as tf:
        data = b"hardlink data"
        base = tarfile.TarInfo(target)
        base.size = len(data)
        base.mode = 0o644
        tf.addfile(base, io.BytesIO(data))
        link = tarfile.TarInfo(name)
        link.type = tarfile.LNKTYPE
        link.linkname = target
        tf.addfile(link)


def make_mode_tar(path, name, mode, data=b"#!/bin/sh\n"):
    with tarfile.open(path, "w") as tf:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = mode
        tf.addfile(info, io.BytesIO(data))


def tempdir():
    return tempfile.TemporaryDirectory(prefix="extract_test_")


def home_dir(base):
    h = Path(base) / "home"
    h.mkdir(parents=True, exist_ok=True)
    return h


def files_under(path):
    root = Path(path)
    if not root.exists():
        return []
    out = []
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            out.append(p.relative_to(root).as_posix())
    return sorted(out)
