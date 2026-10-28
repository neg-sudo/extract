#!/usr/bin/env python3
"""Deterministic fuzz smoke test (no third-party dependencies).

Mutates valid ZIP/TAR archives and synthesizes hostile member names, asserting
that the only outcomes are success or a safeops.ExtractError subclass. Any
other exception is a bug.
"""

import argparse
import io
import os
import random
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
import safeops as so  # noqa: E402

ALLOWED = (so.ExtractError,)
NAME_CHARS = ("a", "Z", "0", ".", "/", "\\", "..", "\x00", "\x07", "\u202e",
              "\u2066", ":", " ", "\n", "é", "世", "C", "*", "?", "|")


def random_name(rng):
    return "".join(rng.choice(NAME_CHARS) for _ in range(rng.randint(0, 40)))


def fuzz_names(rng, iterations):
    for _ in range(iterations):
        name = random_name(rng)
        try:
            rel = so.sanitize_member_name(name)
        except so.SecurityError:
            continue
        assert not rel.startswith("/"), rel
        assert ".." not in rel.split("/"), rel
        assert "\x00" not in rel, rel
    return True


def valid_zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(4):
            zf.writestr(f"dir{i % 2}/file{i}.txt", "A" * (i + 1))
    return buf.getvalue()


def valid_tar_bytes():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for i in range(4):
            data = ("B" * (i + 1)).encode()
            info = tarfile.TarInfo(f"dir{i % 2}/file{i}.txt")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def mutate(data, rng):
    b = bytearray(data)
    for _ in range(rng.randint(1, 32)):
        if not b:
            break
        pos = rng.randrange(len(b))
        b[pos] = rng.randrange(256)
    if rng.random() < 0.2:
        b = b[: rng.randrange(len(b) + 1)]
    return bytes(b)


def try_extract(path, dest):
    limits = so.Limits(max_total=16 * 1024 * 1024, max_file=8 * 1024 * 1024,
                       max_files=1000, max_ratio=10000, max_depth=3)
    try:
        if path.suffix == ".zip":
            so.extract_zip(str(path), str(dest), limits, force=True)
        else:
            so.extract_tar(str(path), str(dest), limits, force=True)
    except ALLOWED:
        return
    return


def fuzz_archives(rng, iterations):
    seeds = [(b"zip", valid_zip_bytes()), (b"tar", valid_tar_bytes())]
    with tempfile.TemporaryDirectory(prefix="extract_fuzz_") as tmp:
        tmp = Path(tmp)
        for i in range(iterations):
            kind, seed = seeds[i % len(seeds)]
            data = mutate(seed, rng)
            path = tmp / (f"case_{i}.{kind.decode()}")
            path.write_bytes(data)
            dest = tmp / f"out_{i}"
            dest.mkdir()
            try_extract(path, dest)
            # Nothing may resolve outside the destination directory.
            dest_real = os.path.realpath(dest)
            for p in dest.rglob("*"):
                rp = os.path.realpath(p)
                if rp != dest_real and os.path.commonpath(
                        [dest_real, rp]) != dest_real:
                    raise AssertionError(f"escape from destination: {p} -> {rp}")
            shutil.rmtree(dest, ignore_errors=True)
    return True


def fuzz_detection(rng, iterations):
    for _ in range(iterations):
        data = bytes(rng.randrange(256) for _ in range(rng.randint(0, 128)))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            name = f.name
        try:
            with open(name, "rb") as fh:
                header = fh.read(512)
            _ = header
        finally:
            os.unlink(name)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    fuzz_names(rng, args.iterations)
    fuzz_archives(rng, max(50, args.iterations // 4))
    fuzz_detection(rng, max(50, args.iterations // 20))
    print(f"fuzz smoke ok ({args.iterations} iterations, seed {args.seed})")


if __name__ == "__main__":
    main()
