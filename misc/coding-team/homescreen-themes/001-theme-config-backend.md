# Task Brief 001 — Theme Config Backend

## Context

`Config` (`backend/config.py`) stores all app settings. `SettingsManager` (`backend/settings_manager.py`) wraps `Config` and exposes values to QML via `Q_PROPERTY`. The `ui` section of `config.json` holds display preferences (`button_layout`, `show_network_indicator`, etc.).

`main.py` defines `APP_DIR = Path(__file__).parent` (currently named `QML_DIR` and `ASSETS_DIR` — the parent is `Path(__file__).parent`). The themes directory lives at `<app_root>/themes/<theme_name>/`.

## Objective

1. Add `theme_name: str` (default `"default"`) to `Config`.
2. Expose two read-only properties on `SettingsManager`:
   - `themeName: str` — the raw theme name string (e.g. `"default"`)
   - `themeDir: str` — the absolute `file://` URL to the theme folder (e.g. `"file:///home/user/opencode/htpcstation/themes/default/"`) — trailing slash required for QML image path concatenation.

## Scope

**`backend/config.py`**
- Add `self._theme_name: str = "default"` to `__init__` (alongside other `ui` fields).
- Add `@property theme_name` getter.
- Add `set_theme_name(name: str)` setter (validates non-empty string, calls `self.save()`).
- In `save()` → `"ui"` dict: add `"theme_name": self._theme_name`.
- In `_load()` → `ui` section: read `ui.get("theme_name", "default")`, strip whitespace, fall back to `"default"` if blank.

**`backend/settings_manager.py`**
- Add `APP_DIR` as a constructor parameter (type `Path`). Store as `self._app_dir`.
- Add `themeNameChanged = Signal()` to the signal block.
- Add `_get_theme_name()` → `self._config.theme_name`.
- Add `_get_theme_dir()` → `"file://" + str(self._app_dir / "themes" / self._config.theme_name) + "/"`.
- Add `themeName = Property(str, fget=_get_theme_name, notify=themeNameChanged)`.
- Add `themeDir = Property(str, fget=_get_theme_dir, notify=themeNameChanged)`.

**`main.py`**
- Define `APP_DIR = Path(__file__).parent` (already implicitly available — make it explicit alongside `QML_DIR`).
- Pass `app_dir=APP_DIR` to `SettingsManager(...)`.

## Non-goals / Later
- No Settings UI for theme switching (future).
- No `setThemeName` slot needed yet (read-only from QML for now).

## Constraints / Caveats
- `Config.save()` has a credentials guard — do not touch that logic. Just add `"theme_name"` to the `"ui"` dict.
- Never construct a second `Config()` instance. `SettingsManager` receives the existing one.
- Signal name must NOT be `themeNameChanged` if there is already a property auto-signal with that name — but since `themeName` is a `Property(str, ...)` with an explicit `notify=`, QML won't auto-generate a conflicting signal. This is safe.
- `themeDir` must end with `/` so QML can do `settings.themeDir + "retrogames-button.png"` without an extra separator.

## Acceptance Criteria
- `Config()` with no existing config file has `theme_name == "default"`.
- `Config()` loading a config with `"ui": {"theme_name": "mytheme"}` has `theme_name == "mytheme"`.
- `Config()` loading a config with blank or missing `theme_name` falls back to `"default"`.
- `SettingsManager.themeDir` ends with `/` and contains the correct absolute path.
- Existing tests still pass (`python3 -m pytest tests/ -q`).
