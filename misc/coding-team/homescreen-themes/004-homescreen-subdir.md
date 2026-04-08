# Task Brief 004 — Move Theme Images into homescreen/ Subdirectory

## Context

Theme images currently live flat in `themes/default/`. All 7 images are homescreen-specific. The new convention is `themes/<name>/homescreen/` for homescreen assets, leaving room for future per-screen theme directories.

`HomeScreen.qml` references images via `settings.themeDir` (which resolves to `file://.../themes/default/`). Two lines concatenate filenames directly onto that base URL.

## Objective

1. Move all 7 images from `themes/default/` into `themes/default/homescreen/`.
2. Update the two image source expressions in `HomeScreen.qml` to insert `"homescreen/"` between `themeDir` and the filename.

## Scope

**Filesystem:**
- `git mv themes/default/home-background.png themes/default/homescreen/home-background.png`
- `git mv themes/default/*-button.png themes/default/homescreen/` (all 6 button images)

**`qml/screens/HomeScreen.qml` — two lines only:**
- Line ~299: `settings.themeDir + "home-background.png"` → `settings.themeDir + "homescreen/home-background.png"`
- Line ~367: `settings.themeDir + homeScreen.tabSlugs[index] + "-button.png"` → `settings.themeDir + "homescreen/" + homeScreen.tabSlugs[index] + "-button.png"`

No other files change.

## Non-goals / Later
- No backend changes — `themeDir` already ends with `/`, no adjustment needed.
- No new tests needed — this is a path string change; existing tests cover `themeDir` format.

## Acceptance Criteria
- `themes/default/` contains only the `homescreen/` subdirectory (no loose `.png` files).
- `themes/default/homescreen/` contains all 7 images.
- All 1931 tests still pass.
