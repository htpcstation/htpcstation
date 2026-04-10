# Task 001 — Filesystem fallback scan when gamelist.xml is missing

## Context

`GameLibrary._scan()` in `backend/library.py:640-645` skips any ROM folder that lacks a `gamelist.xml`. Every system in `SYSTEM_DEFAULTS` (config.py) already has an `extensions` list. When `gamelist.xml` is absent, we should fall back to scanning the folder for files matching those extensions and create minimal Game entries from the filenames.

## Objective

When a system folder has no `gamelist.xml` but its folder name matches a known system in config, scan for ROM files by extension and populate the system with Game entries using cleaned-up filenames as titles.

## Scope

### `backend/library.py` — `_scan()` method only

Replace the early `continue` when `gamelist.xml` doesn't exist (lines 643-645) with a filesystem fallback:

```python
gamelist_file = entry / "gamelist.xml"
folder_name = entry.name
sys_config = self._config.get_system(folder_name)

if gamelist_file.exists():
    games = parse_gamelist(entry)
elif sys_config.extensions:
    # No gamelist.xml but known system — scan for ROM files
    games = _scan_rom_files(entry, folder_name, sys_config.extensions)
else:
    # Unknown system with no gamelist.xml — skip
    continue
```

Add a module-level helper function `_scan_rom_files(system_path, folder_name, extensions)`:

- Iterate `system_path` entries (non-recursive, sorted)
- Keep only files whose suffix (case-insensitive) is in `extensions`
- For each matching file, create a `Game` with:
  - `path`: absolute path to the file
  - `name`: cleaned title from filename (see below)
  - `system_folder`: `folder_name`
  - All other fields: defaults (empty string, 0, False, None)
- Return the list sorted by `name` (case-insensitive)

### Title cleaning

Strip the file extension, then remove anything in parentheses or brackets (including the parens/brackets themselves), then strip leading/trailing whitespace:

```python
import re

def _clean_rom_title(filename: str) -> str:
    name = Path(filename).stem
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)
    return name.strip()
```

Examples:
- `"Super Mario Bros (USA).nes"` → `"Super Mario Bros"`
- `"Zelda [Europe] (Rev 1).gba"` → `"Zelda"`
- `"Castlevania.sfc"` → `"Castlevania"`

### Extension matching

Match case-insensitively: a file `Game.GBA` should match extension `.gba`.

## Non-goals

- Do NOT modify `gamelist.py`, `models.py`, any QML file, or `config.py`.
- Do NOT merge gamelist.xml entries with filesystem results — gamelist.xml is authoritative when present.
- Do NOT persist play stats for filesystem-scanned games (no gamelist.xml to write to).
- Do NOT scan subdirectories recursively — only top-level files in the system folder.

## Tests

Add tests in a new file `tests/test_rom_fallback_scan.py`:

1. **Folder with no gamelist.xml + known system** → games populated from matching files
2. **Folder with no gamelist.xml + unknown system (no extensions)** → system skipped
3. **Folder with gamelist.xml** → gamelist.xml used (not filesystem scan) — existing behavior preserved
4. **Title cleaning** → parentheses, brackets, and combinations stripped correctly
5. **Extension matching is case-insensitive**
6. **Non-matching extensions are ignored**
7. **Files are sorted alphabetically by cleaned name**

## Acceptance criteria

- ROMs in known system folders display with cleaned filenames even without gamelist.xml.
- Existing gamelist.xml-based loading is unchanged.
- All existing + new tests pass.
