# Task 009 — Replace F1/F2 keyboard shortcuts with 1/2

## Context

All context actions (Favorite, Sort, My List, etc.) currently use F1/F2 as keyboard
shortcuts. For HTPC use with compact remote keyboards, number keys are easier to reach.

`isMenu` (F10 → quit dialog) is NOT changed — it is never shown in hint text and is
not a common user action.

## Objective

### 1. `backend/keys.py`

In `isContext1`: replace `Qt.Key.Key_F1` with `Qt.Key.Key_1`, and `Qt.Key.Key_F2`
(alternate layout branch) with `Qt.Key.Key_2`.

In `isContext2`: replace `Qt.Key.Key_F2` with `Qt.Key.Key_2`, and `Qt.Key.Key_F1`
(alternate layout branch) with `Qt.Key.Key_1`.

Do NOT change `isMenu` (Key_F10 stays).

### 2. All QML hint strings

Replace every keyboard-branch hint label:
- `"F1"` → `"1"` (in all contexts: `"F1  Favorite"`, `"[F1]"`, `"[F1] Favorite"`, etc.)
- `"F2"` → `"2"` (same)

Files to update (all keyboard-branch hint strings only — do not touch gamepad branches):

- `qml/screens/HomeScreen.qml` — `"[F1]"` → `"[1]"`
- `qml/screens/GameDetailView.qml` — `"F1  Favorite"`
- `qml/screens/GameGridView.qml` — `"F1  Favorite"`, `"F2  Sort"`, `"Esc / F2  Close"`
- `qml/screens/GameListView.qml` — `"F1  Favorite"`, `"F2  Sort"`, `"Esc / F2  Close"`
- `qml/screens/SteamGameGrid.qml` — `"F1  Favorite"`, `"F2  Sort"`, `"Esc / F2  Close"`
- `qml/screens/SteamGameList.qml` — `"F1  Favorite"`, `"F2  Sort"`, `"Esc / F2  Close"`
- `qml/screens/SteamGameDetail.qml` — `"[F1] Favorite"` in hardcoded footer string
- `qml/screens/MoonlightAppGrid.qml` — `"F1  Favorite"`, `"F2  Sort"`, `"Esc / F2  Close"`
- `qml/screens/MoonlightAppList.qml` — `"F1  Favorite"`, `"F2  Sort"`, `"Esc / F2  Close"`
- `qml/screens/MoonlightAppDetail.qml` — `"[F1] Favorite"` in hardcoded footer string
- `qml/screens/PlexMovieGrid.qml` — `"F1  My List"`, `"F2  Sort / Filter"`, `"Esc / F2  Close"`
- `qml/screens/PlexMovieList.qml` — same
- `qml/screens/PlexMovieDetail.qml` — `"F1  My List"`, `"F2  ..."` (dynamic watch label)
- `qml/screens/PlexShowGrid.qml` — `"F1  My List"`, `"F2  Sort / Filter"`, `"Esc / F2  Close"`
- `qml/screens/PlexShowList.qml` — same
- `qml/screens/PlexShowDetail.qml` — `"F1  My List"`, `"F2  ..."` (dynamic watch label)
- `qml/screens/PlexOnDeckGrid.qml` — `"F1  My List"`, `"F2  View"`, `"Esc / F2  Close"`
- `qml/screens/PlexOnDeckList.qml` — same
- `qml/screens/PlexArtistGrid.qml` — `"F2  Sort"`, `"Esc / F2  Close"`
- `qml/screens/PlexArtistList.qml` — same
- `qml/screens/RecentlyPlayedGrid.qml` — `"F2  View"`, `"Esc / F2  Close"`
- `qml/screens/RecentlyPlayedList.qml` — same
- `qml/screens/LiveTvScreen.qml` — `"F2  Refresh"`
- `qml/screens/ListenScreen.qml` — check for any remaining F1/F2 hint strings

Also update any file-header comments that document the key bindings
(e.g. `// X (F1) → ...`, `// Y (F2) → ...`) to say `1` and `2` instead.

## Non-goals

- Do not change `isMenu` / `Key_F10`.
- Do not change gamepad label branches (those use `keys.context1Label` etc., not "F1").
- Do not change any key handler logic — only the key codes in `keys.py` and the
  display strings in QML.

## Verification

After the change, grep for any remaining `F1` or `F2` in keyboard-branch hint strings
to confirm none were missed. The only acceptable remaining occurrences of `F1`/`F2` are:
- In comments documenting the old mapping (these should be updated too)
- `Key_F10` in `isMenu` (untouched)
