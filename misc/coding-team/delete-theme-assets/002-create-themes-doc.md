# Task 002 — Create themes.md documentation

## Context
Theme image assets have been deleted but all wiring remains. A doc is needed so the user (or a future agent) can re-add themes correctly.

## Objective
Create `htpcstation/docs/themes.md` documenting the theme system.

## Content to include

1. **Overview** — One-liner: themes provide per-screen image assets; the app falls back to styled rectangles when images are missing.

2. **Directory structure** — The app resolves theme assets via `settings.themeDir` which maps to:
   ```
   htpcstation/themes/<theme_name>/
   └── homescreen/
       ├── home-background.png
       ├── retrogames-button.png
       ├── pcgames-button.png
       ├── moonlight-button.png
       ├── plexmedia-button.png
       ├── plexmusic-button.png
       └── settings-button.png
   ```
   Future screens can add their own subdirectories (e.g. `settings/`).

3. **Config** — `config.json` → `ui.theme_name` (string, default `"default"`). `SettingsManager` exposes `themeName` (raw name) and `themeDir` (absolute `file://` URL with trailing slash).

4. **QML consumption** — `HomeScreen.qml` concatenates `settings.themeDir + "homescreen/" + slug + "-button.png"`. Tab slugs are defined in `HomeScreen.tabSlugs`. Background is `home-background.png`. Images that fail to load are hidden; a fallback rectangle with a text label is shown instead.

5. **How to add a new theme** — Create `themes/<name>/homescreen/` with the 7 images above, then set `ui.theme_name` in config to `<name>`.

6. **Wiring locations** (for reference):
   - `backend/config.py` — `_theme_name`, `theme_name`, `set_theme_name`, save/load
   - `backend/settings_manager.py` — `themeName`, `themeDir` properties
   - `qml/screens/HomeScreen.qml` — lines ~303, ~381
   - `tests/test_theme_config.py` — 18 tests covering config + settings

## Non-goals
- Do not document color themes, accent colors, or the `Theme` QML singleton — those are separate from the image theme system.
- Do not modify any code.

## Constraints
- Keep it concise — single file, no more than ~80 lines.
