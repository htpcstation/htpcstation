# Task 001 — Guard theme image sources with themeAvailable property

## Context

The `themes/default/` directory was deleted but `HomeScreen.qml` still tries to load images via `settings.themeDir`. This produces 6 "Cannot open" console warnings on every startup. The fallback rectangles already display correctly — we just need to prevent the Image load attempt when the theme directory doesn't exist.

## Objective

Suppress the console warnings while preserving the theme infrastructure for future use.

## Scope

### `backend/settings_manager.py`
- Add a `themeAvailable` read-only bool property (notify on `themeNameChanged`).
- It should return `True` if the theme directory exists on disk, `False` otherwise.
- The theme directory path is already computed for `themeDir` — reuse that logic. The path (without `file://` prefix) is: `os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes", self._config.theme_name)`.

### `qml/screens/HomeScreen.qml`
- Line ~303 (background image): guard `source` with `settings.themeAvailable`:
  ```qml
  source: (settings && settings.themeAvailable) ? settings.themeDir + "homescreen/home-background.png" : ""
  ```
- Line ~380-381 (button images): add `settings.themeAvailable` to the existing guard:
  ```qml
  source: (settings && settings.themeAvailable && index < homeScreen.tabSlugs.length && homeScreen.tabSlugs[index])
      ? settings.themeDir + "homescreen/" + homeScreen.tabSlugs[index] + "-button.png"
      : ""
  ```

### Tests
- Add tests for `themeAvailable`:
  - Returns `False` when theme directory doesn't exist.
  - Returns `True` when theme directory exists (create a temp dir).
- Add to existing test file `tests/test_theme_config.py`.

## Non-goals
- Don't remove any theme infrastructure.
- Don't change fallback rectangle behavior.
- Don't modify `themeDir` or `themeName` behavior.

## Caveats
- `themeDir` returns a `file://` URL. `themeAvailable` should check the raw filesystem path, not the URL.
