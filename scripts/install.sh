#!/usr/bin/env bash
# extract installer - Universal archive extractor for all platforms
# MIT Licensed - Copyright (c) 2026 extract contributors

set -e

VERSION="1.1.0"
REPO_URL="https://github.com/neg/extract"
INSTALL_DIR="${EXTRACT_INSTALL_DIR:-$HOME/.extract}"
BIN_DIR="${EXTRACT_BIN_DIR:-$HOME/.local/bin}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Darwin*)    echo "macos" ;;
        Linux*)     
            if grep -qEi "(Microsoft|WSL)" /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        CYGWIN*|MINGW*|MSYS*|MINGW32*|MINGW64*) echo "windows" ;;
        *)          echo "unknown" ;;
    esac
}

OS=$(detect_os)

echo -e "${BOLD}extract${NC} v${VERSION} installer"
echo "Platform: $OS"
echo ""

# Check for Python
if ! command -v python3 >/dev/null 2>&1; then
    if command -v python >/dev/null 2>&1; then
        PYTHON=python
    else
        error "Python 3 is required but not found. Please install Python 3."
    fi
else
    PYTHON=python3
fi

success "Found $PYTHON"

# Create directories
info "Installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"/{bin,lib}
mkdir -p "$BIN_DIR"

# Install files from local repo if available, else download
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -f "$REPO_ROOT/bin/extract" ] && [ -f "$REPO_ROOT/lib/extract.py" ]; then
    info "Installing from local files..."
    cp "$REPO_ROOT/bin/extract" "$INSTALL_DIR/bin/"
    cp "$REPO_ROOT/lib/extract.py" "$INSTALL_DIR/lib/"
else
    info "Downloading from GitHub..."
    mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/lib"
    curl -fsSL "$REPO_URL/raw/main/bin/extract" -o "$INSTALL_DIR/bin/extract" || \
        wget -qO "$INSTALL_DIR/bin/extract" "$REPO_URL/raw/main/bin/extract" || \
        error "Failed to download extract"
    curl -fsSL "$REPO_URL/raw/main/lib/extract.py" -o "$INSTALL_DIR/lib/extract.py" || \
        wget -qO "$INSTALL_DIR/lib/extract.py" "$REPO_URL/raw/main/lib/extract.py" || \
        error "Failed to download extract.py"
fi

chmod +x "$INSTALL_DIR/bin/extract"
chmod +x "$INSTALL_DIR/lib/extract.py"

# Create symlinks
ln -sf "$INSTALL_DIR/bin/extract" "$BIN_DIR/extract"
ln -sf "$INSTALL_DIR/bin/extract" "$BIN_DIR/x"

success "Installed to $BIN_DIR/extract (alias: x)"

# PATH setup
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    warn "$BIN_DIR is not in your PATH"
    echo ""
    echo "Add this to your shell configuration:"
    echo -e "  ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
    echo ""
    
    # Try to add automatically
    SHELL_RC=""
    case "$SHELL" in
        */zsh) SHELL_RC="$HOME/.zshrc" ;;
        */bash) 
            if [ -f "$HOME/.bashrc" ]; then SHELL_RC="$HOME/.bashrc"
            elif [ -f "$HOME/.bash_profile" ]; then SHELL_RC="$HOME/.bash_profile"
            fi
            ;;
        */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
    esac
    
    if [ -n "$SHELL_RC" ] && [ -f "$SHELL_RC" ]; then
        if ! grep -q '.local/bin' "$SHELL_RC"; then
            read -p "Add to $SHELL_RC automatically? [Y/n] " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo '' >> "$SHELL_RC"
                echo '# extract' >> "$SHELL_RC"
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
                success "Added to $SHELL_RC"
                info "Run 'source $SHELL_RC' or open a new terminal"
            fi
        fi
    fi
fi

# Suggest missing tools
echo ""
info "Checking for common archive tools..."
for tool in unzip tar gzip bzip2 xz; do
    if command -v $tool >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $tool"
    else
        echo -e "  ${YELLOW}○${NC} $tool (recommended)"
    fi
done
for tool in 7z unrar zstd; do
    if command -v $tool >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $tool"
    else
        echo -e "  ${DIM}○${NC} $tool (optional)"
    fi
done

echo ""
success "Installation complete!"
echo -e "Run ${BOLD}extract --help${NC} to get started"
