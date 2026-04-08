# Task Brief 003 — Documentation Update

## Context

Checkpoint 33 implemented the homescreen theme system. Three docs need updating per the project's documentation maintenance rules.

## Objective

Update `docs/resume-project.md`, `docs/architecture.md`, and `docs/changelog.md` to reflect what shipped.

## Scope

### `docs/resume-project.md`
- Bump checkpoint number to **CP33** in the heading.
- Update **"What's new since CP31"** → **"What's new since CP32"** and replace the content with a summary of what shipped in CP33:
  - Theme system V1: `themes/<name>/` directory, `home-background.png` + `*-button.png` per tab
  - `Config.theme_name` + `SettingsManager.themeName` / `themeDir` properties
  - `HomeScreen` rewritten as two-level launcher: background image + centered image buttons; tab content only loads on A-press; B returns to launcher and destroys the tab screen (fixes Plex eager-load slowness)
  - `tabSlugs` added alongside `tabNames`/`tabSources`; Settings tab unified into `_allTabs` loop
- Update **"Next milestone"** to: M7 — Local Music tab V1.
- Update test count to **1931**.

### `docs/architecture.md`

**Codebase Structure section** — update `HomeScreen.qml` description:
> `HomeScreen.qml` — Two-level launcher: Level 1 = background image + centered image buttons (theme-driven); Level 2 = tab content loaded on demand. Tab content destroyed on back() to prevent eager network calls. MediaPlayer + AudioOutput, global X play/pause, MPV running state, subtitle overlay trigger.

**Theme System section** — replace the existing note with:
```
### Theme System
- Themes live in `themes/<name>/` relative to the app root.
- Active theme set via `Config.theme_name` (default: `"default"`), persisted in `config.json` under `"ui"`.
- `SettingsManager.themeName` (str) and `themeDir` (str, `file://` URL ending in `/`) expose the theme to QML.
- `APP_DIR = Path(__file__).parent` defined in `main.py`; passed to `SettingsManager` as `app_dir`.
- Theme assets for the homescreen: `home-background.png` (full-screen background), `<slug>-button.png` per tab (slugs: `retrogames`, `pcgames`, `moonlight`, `plexmedia`, `plexmusic`, `settings`).
- Fallback: if a button image fails to load (`Image.status !== Image.Ready`), a plain rectangle + text label is shown.
- Color palette swap (future 4b/4c work) is separate from the image theme system.
```

**Config File Structure section** — add `"theme_name": "default"` to the `"ui"` block in the example JSON.

**Gotchas — QML section** — add one entry:
> **`HomeScreen` tab content is loaded on demand** — `Loader.source` starts as `""`. Set it imperatively on A-press; clear it in `returnFocusToTabBar()` to destroy the screen and stop network calls. Do not bind `Loader.source` to any property.

### `docs/changelog.md`

Prepend a new entry at the top:
```
## CP33 — Homescreen Theme System V1

Task briefs: `misc/coding-team/homescreen-themes/`

- 001: `Config.theme_name` + `SettingsManager.themeName`/`themeDir` (21 new tests)
- 002: `HomeScreen.qml` rewritten as two-level launcher with theme image buttons
- 003: Docs update
```

## Non-goals / Later
- No changes to any Python or QML source files.
- Do not update `milestones.md` — no milestone was completed.
