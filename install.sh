#!/usr/bin/env bash
# extract installer - Universal archive extractor
# MIT Licensed

set -e

REPO_DIR="${HOME}/.extract"
BIN_DIR="${HOME}/.local/bin"

echo "Installing extract..."
mkdir -p "$BIN_DIR"

# Install files
mkdir -p "$REPO_DIR"/{bin,lib}
cp "$(dirname "$0")/bin/extract" "$REPO_DIR/bin/" 2>/dev/null || cp bin/extract "$REPO_DIR/bin/"
cp "$(dirname "$0")/lib/extract.py" "$REPO_DIR/lib/" 2>/dev/null || cp lib/extract.py "$REPO_DIR/lib/"
cp "$(dirname "$0")/lib/safeops.py" "$REPO_DIR/lib/" 2>/dev/null || cp lib/safeops.py "$REPO_DIR/lib/"
chmod +x "$REPO_DIR/bin/extract"
chmod +x "$REPO_DIR/lib/extract.py"

# Create symlinks
ln -sf "$REPO_DIR/bin/extract" "$BIN_DIR/extract"
ln -sf "$REPO_DIR/bin/extract" "$BIN_DIR/x"

# Add to PATH if needed
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "Add $BIN_DIR to your PATH:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "Add this to your shell rc file (~/.bashrc, ~/.zshrc, etc.)"
fi

echo "✓ extract installed successfully!"
echo "  Run 'extract --help' to get started"
