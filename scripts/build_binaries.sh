#!/usr/bin/env bash
# Build a standalone binary and a universal zipapp for extract.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="$(python3 - <<'PY'
import re
from pathlib import Path
m = re.search(r'VERSION = "([^"]+)"', Path('lib/extract.py').read_text())
print(m.group(1) if m else '0.0.0')
PY
)"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
rm -rf lib/__pycache__
mkdir -p dist

echo "==> zipapp"
python3 -m zipapp lib -m "extract:main" --compress -p "/usr/bin/env python3" \
  -o "dist/extract-${VERSION}.pyz"
chmod +x "dist/extract-${VERSION}.pyz"

if command -v pyinstaller >/dev/null 2>&1; then
  echo "==> pyinstaller one-file binary"
  pyinstaller --clean --noconfirm --onefile --name extract --paths lib lib/extract.py
  cp "dist/extract" "dist/extract-${OS}-${ARCH}"
else
  echo "pyinstaller not found; skipping native binary (pip install pyinstaller)" >&2
fi

echo "==> checksums"
( cd dist && sha256sum extract-* > SHA256SUMS )
cat dist/SHA256SUMS
