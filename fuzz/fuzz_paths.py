#!/usr/bin/env python3
"""Atheris target: member-name sanitization must never escape or crash."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import safeops as so  # noqa: E402

try:
    import atheris
except ImportError:  # pragma: no cover
    atheris = None


def TestOneInput(data):
    try:
        name = data.decode("utf-8", "surrogateescape")
    except Exception:
        return
    try:
        rel = so.sanitize_member_name(name)
    except so.SecurityError:
        return
    assert not rel.startswith("/")
    assert ".." not in rel.split("/")


def main():
    if atheris is None:
        print("install atheris: pip install atheris", file=sys.stderr)
        return 1
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
    return 0


if __name__ == "__main__":
    sys.exit(main())
