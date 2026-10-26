# extract installer for Windows (PowerShell)
# MIT Licensed - Copyright (c) 2026 extract contributors

param(
    [string]$InstallDir = "$env:USERPROFILE\.extract",
    [string]$BinDir = "$env:USERPROFILE\.local\bin"
)

$Version = "2.0.0"

Write-Host "extract v$Version installer" -ForegroundColor Cyan
Write-Host "Platform: Windows" -ForegroundColor Gray
Write-Host ""

# Check for Python
$python = $null
foreach ($cmd in @("python3", "python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $python = $cmd
        break
    }
}

if (-not $python) {
    Write-Host "✗ Python 3 is required but not found." -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Found $python" -ForegroundColor Green

# Create directories
Write-Host "ℹ Installing to $InstallDir" -ForegroundColor Blue
New-Item -ItemType Directory -Force -Path $InstallDir\bin, $InstallDir\lib | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

# Install files
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = $ScriptDir

if ((Test-Path "$RepoRoot\bin\extract") -and (Test-Path "$RepoRoot\lib\extract.py")) {
    Write-Host "ℹ Installing from local files..." -ForegroundColor Blue
    Copy-Item "$RepoRoot\bin\extract" "$InstallDir\bin\extract" -Force
    Copy-Item "$RepoRoot\lib\extract.py" "$InstallDir\lib\extract.py" -Force
} else {
    Write-Host "ℹ Downloading from GitHub..." -ForegroundColor Blue
    $baseUrl = "https://github.com/neg-sudo/extract/raw/main"
    Invoke-WebRequest -Uri "$baseUrl/bin/extract" -OutFile "$InstallDir\bin\extract" -UseBasicParsing
    Invoke-WebRequest -Uri "$baseUrl/lib/extract.py" -OutFile "$InstallDir\lib\extract.py" -UseBasicParsing
}

# Create wrapper scripts for Windows
$extractBat = @"
@echo off
setlocal
set LIB_PATH=%USERPROFILE%\.extract\lib\extract.py
$python "%LIB_PATH%" %*
"@

$extractCmd = @"
@echo off
setlocal
set LIB_PATH=%USERPROFILE%\.extract\lib\extract.py
py "%LIB_PATH%" %*
"@

# Try to use best Python command
$extractWrapper = @"
@echo off
setlocal
REM Try python3, python, py
where python3 >nul 2>&1 && (python3 "%USERPROFILE%\.extract\lib\extract.py" %* && exit /b)
where python >nul 2>&1 && (python "%USERPROFILE%\.extract\lib\extract.py" %* && exit /b)
where py >nul 2>&1 && (py "%USERPROFILE%\.extract\lib\extract.py" %* && exit /b)
echo Python not found
exit /b 1
"@

Set-Content -Path "$BinDir\extract.cmd" -Value $extractWrapper
Set-Content -Path "$BinDir\x.cmd" -Value $extractWrapper

# Also create PowerShell function/script
$extractPs1 = @"
#!/usr/bin/env pwsh
& py "$env:USERPROFILE\.extract\lib\extract.py" @args
"@
Set-Content -Path "$BinDir\extract.ps1" -Value $extractPs1

Write-Host "✓ Installed to $BinDir\extract.cmd (alias: x.cmd)" -ForegroundColor Green

# Add to PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
    Write-Host "⚠ $BinDir is not in your PATH" -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "Add to PATH automatically? [Y/n]"
    if ($response -ne "n" -and $response -ne "N") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$BinDir", "User")
        Write-Host "✓ Added to user PATH" -ForegroundColor Green
        Write-Host "ℹ Restart your terminal for changes to take effect" -ForegroundColor Blue
    } else {
        Write-Host "Add manually: Settings > System > Environment Variables" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Checking for archive tools..." -ForegroundColor Blue
foreach ($tool in @("tar")) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) {
        Write-Host "  ✓ $tool" -ForegroundColor Green
    }
}
if (Get-Command "7z" -ErrorAction SilentlyContinue) {
    Write-Host "  ✓ 7z" -ForegroundColor Green
} else {
    Write-Host "  ○ 7z (optional - install from 7-zip.org)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "✓ Installation complete!" -ForegroundColor Green
Write-Host "Run 'extract --help' in a new terminal to get started" -ForegroundColor Cyan
