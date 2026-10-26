#!/usr/bin/env bash
# extract installer - Universal archive extractor for all platforms
# MIT Licensed - Copyright (c) 2026 extract contributors

set -e

OWNER="neg-sudo"
REPO="extract"
VERSION="2.0.0"
BRANCH="main"
RAW_BASE="https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}"

INSTALL_DIR="${EXTRACT_INSTALL_DIR:-$HOME/.extract}"
BIN_DIR="${EXTRACT_BIN_DIR:-$HOME/.local/bin}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

info()    { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC} $1"; }
error()   { echo -e "${RED}✗${NC} $1" >&2; exit 1; }

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
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    error "Python 3 is required but not found. Please install Python 3."
fi

success "Found $PYTHON"

# Create directories
info "Installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/lib"
mkdir -p "$BIN_DIR"

# Download helper (atomic: never clobbers an existing file on failure)
download() {
    local url="$1" out="$2" tmp
    tmp="$(mktemp "${out}.XXXXXX")" || return 1
    if command -v curl >/dev/null 2>&1; then
        if ! curl -fsSL "$url" -o "$tmp"; then rm -f "$tmp"; return 1; fi
    elif command -v wget >/dev/null 2>&1; then
        if ! wget -qO "$tmp" "$url"; then rm -f "$tmp"; return 1; fi
    else
        rm -f "$tmp"
        error "Need curl or wget to download: $url"
    fi
    chmod 0755 "$tmp" 2>/dev/null || true
    mv -f "$tmp" "$out"
}

# Prefer local repo files when running from a checkout; otherwise download.
LOCAL_ROOT=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CANDIDATE="$(dirname "$SCRIPT_DIR")"
    if [ -f "$CANDIDATE/bin/extract" ] && [ -f "$CANDIDATE/lib/extract.py" ]; then
        LOCAL_ROOT="$CANDIDATE"
    fi
fi

if [ -n "$LOCAL_ROOT" ]; then
    info "Installing from local files..."
    cp "$LOCAL_ROOT/bin/extract" "$INSTALL_DIR/bin/extract"
    cp "$LOCAL_ROOT/lib/extract.py" "$INSTALL_DIR/lib/extract.py"
else
    info "Downloading from GitHub..."
    download "$RAW_BASE/bin/extract" "$INSTALL_DIR/bin/extract" \
        || error "Failed to download $RAW_BASE/bin/extract"
    download "$RAW_BASE/lib/extract.py" "$INSTALL_DIR/lib/extract.py" \
        || error "Failed to download $RAW_BASE/lib/extract.py"
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

    SHELL_RC=""
    case "$SHELL" in
        */zsh)  SHELL_RC="$HOME/.zshrc" ;;
        */bash)
            if [ -f "$HOME/.bashrc" ]; then SHELL_RC="$HOME/.bashrc"
            elif [ -f "$HOME/.bash_profile" ]; then SHELL_RC="$HOME/.bash_profile"
            fi
            ;;
        */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
    esac

    if [ -n "$SHELL_RC" ] && [ -f "$SHELL_RC" ]; then
        if ! grep -q '.local/bin' "$SHELL_RC" 2>/dev/null; then
            if [ -t 0 ]; then
                read -r -p "Add to $SHELL_RC automatically? [Y/n] " -n 1 REPLY
                echo
                if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                    {
                        echo ''
                        echo '# extract'
                        echo 'export PATH="$HOME/.local/bin:$PATH"'
                    } >> "$SHELL_RC"
                    success "Added to $SHELL_RC"
                    info "Run 'source $SHELL_RC' or open a new terminal"
                fi
            else
                info "Non-interactive run; not modifying $SHELL_RC"
            fi
        fi
    fi
fi

# Suggest missing tools
echo ""
info "Checking for common archive tools..."
for tool in unzip tar gzip bzip2 xz; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $tool"
    else
        echo -e "  ${YELLOW}○${NC} $tool (recommended)"
    fi
done
for tool in 7z unrar zstd; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $tool"
    else
        echo -e "  ${DIM}○${NC} $tool (optional)"
    fi
done

echo ""
success "Installation complete!"
echo -e "Run ${BOLD}extract --help${NC} to get started"
