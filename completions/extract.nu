# extract Nushell completion
export extern extract [
    ...files: path
    --verbose(-v) --list(-l) --force(-f) --dry-run(-n) --test(-t)
    --info(-i) --recursive(-r) --json --quiet(-q) --tui
    --max-size: string --max-file-size: string --max-files: int
    --max-ratio: float --max-depth: int --include: string
    --search: string --grep: string --strict --no-exec
    --allow-symlinks --preserve-perms --sandbox --delete-nested
]

