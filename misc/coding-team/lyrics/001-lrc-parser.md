# Task Brief 001 — LRC parser

## Context
New file. No existing code to modify. This is a pure utility used by the lyrics fetch task (002).

## Objective
Create `backend/lrc_parser.py` with a single public function `parse_lrc(text: str) -> list[dict]`.

## Scope
**New file:** `backend/lrc_parser.py`
**New test file:** `tests/test_lrc_parser.py`

## Spec

### `parse_lrc(text: str) -> list[dict]`

Input: raw LRC string as returned by LRCLIB `syncedLyrics` field.

LRC line format: `[mm:ss.xx] lyric text` — where `xx` is hundredths of a second.
Blank-text lines (e.g. `[01:23.45] `) are valid — include them with `text: ""`.
Lines that don't match the timestamp pattern are ignored (header tags like `[ar:...]`, `[ti:...]`).

Output: list of dicts sorted ascending by `ms`, each:
```python
{"ms": int, "text": str}
```
`ms` = milliseconds, computed as `minutes*60000 + seconds*1000 + hundredths*10`.

Empty input or no parseable lines → return `[]`.

### `parse_plain(text: str) -> list[dict]`

Input: raw plain-text lyrics string (LRCLIB `plainLyrics`).

Output: list of dicts, one per non-empty line, all with `ms: -1`:
```python
{"ms": -1, "text": str}
```
Empty input → return `[]`.

## Constraints
- No dependencies beyond stdlib.
- Both functions must handle `None` input gracefully (treat as empty string).

## Acceptance criteria
Tests cover:
- Standard LRC line parsing (ms calculation correct)
- Multiple timestamps on one line (e.g. `[00:10.00][00:20.00] text`) — emit one entry per timestamp
- Header tags ignored
- Blank-text lines included
- Lines out of order in input → output sorted by ms
- Empty / None input → `[]`
- `parse_plain`: each non-empty line becomes `{ms: -1, text: ...}`
