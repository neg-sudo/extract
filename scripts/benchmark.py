#!/usr/bin/env python3
"""Reproducible native-extraction benchmark for extract.

Generates archives locally, extracts them through the real CLI, and reports
wall time, throughput, and files per second. No network access.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "lib" / "extract.py"


def payload(total, files):
    per = max(1, total // max(1, files))
    return per


def make_zip(path, total_bytes, files):
    per = payload(total_bytes, files)
    chunk = (b"extract benchmark payload\n" * (per // 26 + 1))[:per]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for i in range(files):
            zf.writestr(f"dir{i % 100}/file{i:06d}.txt", chunk)
    return path


def make_tar_gz(path, total_bytes, files):
    per = payload(total_bytes, files)
    chunk = (b"extract benchmark payload\n" * (per // 26 + 1))[:per]
    with tarfile.open(path, "w:gz") as tf:
        for i in range(files):
            name = f"dir{i % 100}/file{i:06d}.txt"
            info = tarfile.TarInfo(name)
            info.size = len(chunk)
            info.mode = 0o644
            tf.addfile(info, __import__("io").BytesIO(chunk))
    return path


def run_case(label, archive, out, repeats):
    best = None
    for _ in range(repeats):
        shutil.rmtree(out, ignore_errors=True)
        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, str(EXTRACT), "--json", "--no-flatten", "-C",
             str(out), "-f", str(archive)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        elapsed = time.perf_counter() - start
        if result.returncode != 0:
            print(f"{label}: FAILED ({result.returncode})\n{result.stderr}")
            return None
        data = json.loads(result.stdout)
        if best is None or elapsed < best[0]:
            best = (elapsed, data)
    elapsed, data = best
    nbytes = data.get("bytes_written", 0)
    files = data.get("files", 0)
    mibs = (nbytes / (1024 * 1024)) / elapsed if elapsed else 0
    fps = files / elapsed if elapsed else 0
    return label, files, nbytes, elapsed, mibs, fps


def human(n):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.2f} {unit}"
        n /= 1024.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-mb", type=int, default=10)
    parser.add_argument("--files", type=int, default=1000)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--keep", action="store_true",
                        help="keep generated archives and output")
    args = parser.parse_args()

    if not EXTRACT.exists():
        print(f"missing {EXTRACT}", file=sys.stderr)
        return 1

    total = args.size_mb * 1024 * 1024
    work = Path(tempfile.mkdtemp(prefix="extract_bench_"))
    home = work / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    os.environ["HOME"] = str(home)

    cases = []
    try:
        print(f"generating {args.files} files / {args.size_mb} MiB ...")
        zip_path = make_zip(work / "bench.zip", total, args.files)
        tar_path = make_tar_gz(work / "bench.tar.gz", total, args.files)
        cases.append(("zip", zip_path))
        cases.append(("tar.gz", tar_path))

        print(f"{'format':<10}{'files':>8}{'bytes':>12}{'seconds':>10}"
              f"{'MiB/s':>10}{'files/s':>12}")
        for label, archive in cases:
            result = run_case(label, archive, work / ("out_" + label),
                              args.repeat)
            if not result:
                continue
            lbl, files, nbytes, elapsed, mibs, fps = result
            print(f"{lbl:<10}{files:>8}{human(nbytes):>12}{elapsed:>10.3f}"
                  f"{mibs:>10.1f}{fps:>12.0f}")
    finally:
        if args.keep:
            print(f"kept: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
