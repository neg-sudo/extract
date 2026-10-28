# TUI

```bash
extract --tui archive.zip
```

`--tui` opens a curses browser for native ZIP and TAR archives. It needs an
interactive terminal; otherwise it falls back to a plain listing.

## Keys

| Key | Action |
| --- | ------ |
| `↑` / `k` | Move up |
| `↓` / `j` | Move down |
| `PgUp` / `PgDn` | Page |
| `Space` | Toggle selection |
| `a` | Select all / clear |
| `/` | Search and filter names |
| `Enter` | Apply search |
| `Esc` | Clear search / quit |
| `e` | Extract selected (or the highlighted entry) |
| `q` | Quit |

Selected entries are extracted with the same security core as the CLI:
sanitized names, safe writes, and limits. A filter that matches nothing is
ignored, so you can always see the full list.

## Non-interactive use

For scripts, prefer deterministic flags instead of the TUI:

```bash
extract --list --json archive.zip
extract --include 'src/*' archive.zip
```
