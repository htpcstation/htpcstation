# Image Themes

Themes provide per-screen image assets (backgrounds, button icons). When a
theme image is missing or fails to load, the app falls back to styled
rectangles with text labels.

---

## Directory structure

`SettingsManager.themeDir` resolves to an absolute `file://` URL pointing at:

```
themes/<theme_name>/
  homescreen/
    home-background.png
    retrogames-button.png
    pcgames-button.png
    moonlight-button.png
    plexmedia-button.png
    plexmusic-button.png
    settings-button.png
```

Future screens can add subdirectories (e.g. `settings/`).

## Configuration

In `config.json`:

```json
{ "ui": { "theme_name": "default" } }
```

`SettingsManager` exposes two properties:

| Property    | Type   | Description                                         |
|-------------|--------|-----------------------------------------------------|
| `themeName` | string | Raw theme name from config                          |
| `themeDir`  | string | Absolute `file://` URL with trailing slash           |

## QML consumption

`HomeScreen.qml` builds image paths by concatenating:

```
settings.themeDir + "homescreen/" + slug + "-button.png"
```

- Tab slugs are defined in `HomeScreen.tabSlugs`.
- Background path: `settings.themeDir + "homescreen/home-background.png"`.
- If an image fails to load it is hidden and a fallback rectangle with a text
  label is shown instead.
- All `Image` elements loading from `Settings.themeDir` (and from runtime paths
  across the whole app) have `asynchronous: true` and `cache: true` — decoding
  happens off the main thread and decoded images are retained in Qt's image cache.

## Adding a new theme

1. Create `themes/<name>/homescreen/` with the 7 PNG files listed above.
2. Set `ui.theme_name` to `<name>` in `config.json` (or via the settings UI).

## Wiring locations

| Area               | File                                | Notes                                          |
|--------------------|-------------------------------------|-------------------------------------------------|
| Config layer       | `backend/config.py`                 | `_theme_name`, `theme_name`, `set_theme_name`  |
| Settings bridge    | `backend/settings_manager.py`       | `themeName`, `themeDir` properties              |
| QML UI             | `qml/screens/HomeScreen.qml`       | Image sources (~line 303, ~381)                 |
| Tests              | `tests/test_theme_config.py`        | 18 tests covering config + settings             |

> **Note:** This documents the *image* theme system only. Color themes, accent
> colors, and the `Theme` QML singleton are separate concerns.
