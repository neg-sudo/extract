# Build a standalone extract.exe and checksums on Windows.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$version = (Select-String -Path "lib/extract.py" -Pattern 'VERSION = "([^"]+)"').Matches[0].Groups[1].Value
New-Item -ItemType Directory -Force dist | Out-Null

Write-Host "==> zipapp"
python -m zipapp lib -m "extract:main" -p "/usr/bin/env python3" -o "dist/extract-$version.pyz"

if (Get-Command pyinstaller -ErrorAction SilentlyContinue) {
    Write-Host "==> pyinstaller one-file binary"
    pyinstaller --clean --noconfirm --onefile --name extract --paths lib lib/extract.py
    Copy-Item "dist/extract.exe" "dist/extract-windows-$env:PROCESSOR_ARCHITECTURE.exe"
} else {
    Write-Warning "pyinstaller not found; skipping native binary (pip install pyinstaller)"
}

Write-Host "==> checksums"
Get-ChildItem dist -File | Where-Object { $_.Name -like "extract-*" } | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    "$hash  $($_.Name)"
} | Set-Content dist/SHA256SUMS
Get-Content dist/SHA256SUMS
