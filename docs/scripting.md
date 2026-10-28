# Scripting and CI

## Exit codes

Branch on meaning, not on messages:

```bash
extract --check release.zip
case $? in
  0) echo ok ;;
  2) echo "corrupted archive" ;;
  3) echo "security limit or unsafe path" ;;
  4) echo "checksum mismatch" ;;
  5) echo "password required" ;;
  6) echo "unsupported format" ;;
  *) echo "extraction error" ;;
esac
```

## JSON

```bash
extract --json -C out release.zip
```

```json
{
  "archive": "/abs/release.zip",
  "bytes_written": 582193021,
  "directories": 41,
  "duration_ms": 812,
  "exit_code": 0,
  "files": 1842,
  "format": "zip",
  "output": "/abs/out",
  "skipped": 0,
  "status": "success",
  "warnings": []
}
```

Errors include `status: "error"`, an `error` message, and the same `exit_code`.

## Verifying downloads

```bash
curl -fSLO https://example.com/release.tar.gz
curl -fSLO https://example.com/release.tar.gz.sha256
extract --verify release.tar.gz
extract -C /opt/release release.tar.gz
```

Or supply the digest directly:

```bash
extract --sha256 "$DIGEST" -C out release.tar.gz
```

## Hardened CI container

```bash
extract \
  --max-size 2G \
  --max-file-size 512M \
  --max-files 50000 \
  --max-ratio 100 \
  --max-depth 1 \
  --no-exec \
  -C /tmp/out "$ARTIFACT"
```

## GitHub Actions

```yaml
- name: Install extract
  run: curl -fsSL https://raw.githubusercontent.com/neg-sudo/extract/main/scripts/install.sh | bash
- name: Extract artifact
  run: |
    export PATH="$HOME/.local/bin:$PATH"
    extract --check artifact.zip
    extract --json -C build artifact.zip
```

## Parallel archives

```bash
extract -j 4 --parallel downloads/*.zip
```

The exit code is the highest severity encountered.

## Remote archives

```bash
extract --list https://example.com/data.tar.gz
extract https://example.com/data.tar.gz
```

Remote archives are downloaded to a temporary directory first. For repeated
selective extraction, download once and use `--include`.
