#!/usr/bin/env python3
"""Atheris target: hostile ZIP bytes must fail safely, never crash."""

import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import safeops as so  # noqa: E402

try:
    import atheris
except ImportError:  # pragma: no cover
    atheris = None

LIMITS = so.Limits(max_total=8 * 1024 * 1024, max_file=4 * 1024 * 1024,
                   max_files=500, max_ratio=10000, max_depth=2)


def TestOneInput(data):
    if not data:
        return
    with tempfile.TemporaryDirectory(prefix="extract_atheris_") as tmp:
        path = os.path.join(tmp, "f.zip")
        with open(path, "wb") as f:
            f.write(data)
        dest = os.path.join(tmp, "out")
        os.mkdir(dest)
        try:
            so.extract_zip(path, dest, LIMITS, force=True)
        except so.ExtractError:
            pass
        except (zipfile.BadZipFile, NotImplementedError):
            pass


def main():
    if atheris is None:
        print("install atheris: pip install atheris", file=sys.stderr)
        return 1
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
    return 0


if __name__ == "__main__":
    sys.exit(main())
