# Task 006 — Theme foundation

> Full spec in `misc/coding-team/ui-redesign/task-sheet.md`.
> Test command: `python3 -m pytest tests/ -q`

## Files to change
- `qml/Theme.qml`
- `backend/config.py`
- `backend/settings_manager.py`

---

## A. Palette — `qml/Theme.qml`

Replace the three background palette vars:

```qml
// Before
readonly property color _bg:          "#1a1a2e"
readonly property color _surface:     "#16213e"
readonly property color _surfaceHigh: "#0f3460"

// After
readonly property color _bg:          "#111111"
readonly property color _surface:     "#1c1c1c"
readonly property color _surfaceHigh: "#2a2a2a"
```

Remove the `_accent` palette var entirely (it becomes a computed property —
see section C).

---

## B. Typography — `qml/Theme.qml`

```qml
// Before
readonly property string fontFamily: "Sans"

// After
readonly property string fontFamily:       "Liberation Sans"
readonly property int    fontWeightNormal: Font.Normal
readonly property int    fontWeightBold:   Font.Bold
```

Do not change any `font.bold: true` usages elsewhere — they are correct as-is.

---

## C. Runtime-overridable accent + focus ring colors

### `qml/Theme.qml`

Remove `readonly property color _accent: "#e94560"`.

Replace the two tokens that referenced `_accent` with settings-driven
computed properties (not `readonly` — they must react to `settings` changes):

```qml
property color colorAccent:    settings ? settings.accentColor    : "#e94560"
property color colorFocusRing: settings ? settings.focusRingColor : "#e94560"
```

Update `colorHighlight` to derive from the property (not the removed `_accent`):
```qml
property color colorHighlight: Qt.rgba(colorAccent.r, colorAccent.g, colorAccent.b, 0.15)
```

`colorPrimary` and `colorTabUnderline` already alias `colorAccent` — no
change needed there.

### `backend/config.py`

1. In `__init__`, after `self._theme_name = "default"`, add:
   ```python
   self._accent_color: str = "#e94560"
   self._focus_ring_color: str = "#e94560"
   ```

2. Add properties and setters (after the `theme_name` property block):
   ```python
   @property
   def accent_color(self) -> str:
       return self._accent_color

   def set_accent_color(self, color: str) -> None:
       color = color.strip()
       if not color.startswith("#") or len(color) not in (4, 7, 9):
           logger.warning("set_accent_color: invalid value %r — ignored", color)
           return
       self._accent_color = color
       self.save()

   @property
   def focus_ring_color(self) -> str:
       return self._focus_ring_color

   def set_focus_ring_color(self, color: str) -> None:
       color = color.strip()
       if not color.startswith("#") or len(color) not in (4, 7, 9):
           logger.warning("set_focus_ring_color: invalid value %r — ignored", color)
           return
       self._focus_ring_color = color
       self.save()
   ```

3. In `save()`, inside the `"ui"` dict, add:
   ```python
   "accent_color": self._accent_color,
   "focus_ring_color": self._focus_ring_color,
   ```

4. In `_load()`, inside the `ui` block, add:
   ```python
   raw_accent = ui.get("accent_color", "").strip()
   if raw_accent.startswith("#") and len(raw_accent) in (4, 7, 9):
       self._accent_color = raw_accent
   raw_focus = ui.get("focus_ring_color", "").strip()
   if raw_focus.startswith("#") and len(raw_focus) in (4, 7, 9):
       self._focus_ring_color = raw_focus
   ```

### `backend/settings_manager.py`

Follow the exact same pattern as `themeName` / `setThemeName`.

1. Add two signals alongside `themeNameChanged`:
   ```python
   accentColorChanged = Signal()
   focusRingColorChanged = Signal()
   ```

2. Add two getter methods:
   ```python
   def _get_accent_color(self) -> str:
       return self._config.accent_color

   def _get_focus_ring_color(self) -> str:
       return self._config.focus_ring_color
   ```

3. Add two Q_PROPERTYs alongside `themeName`:
   ```python
   accentColor = Property(str, fget=_get_accent_color, notify=accentColorChanged)
   focusRingColor = Property(str, fget=_get_focus_ring_color, notify=focusRingColorChanged)
   ```

4. Add two `@Slot` setters:
   ```python
   @Slot(str)
   def setAccentColor(self, color: str) -> None:
       self._config.set_accent_color(color)
       self.accentColorChanged.emit()

   @Slot(str)
   def setFocusRingColor(self, color: str) -> None:
       self._config.set_focus_ring_color(color)
       self.focusRingColorChanged.emit()
   ```

---

## D. Focus ring radius — `qml/Theme.qml`

```qml
// Before
readonly property int focusRingRadius: 4

// After
readonly property int focusRingRadius: 10
```

---

## E. Scale animation tokens — `qml/Theme.qml`

Add two new tokens (used by Task 007):
```qml
readonly property real focusScale:         1.05
readonly property int  focusScaleDuration: 120
```

---

## Constraints / Caveats

- `colorAccent` and `colorFocusRing` must be `property` (not `readonly
  property`) in `Theme.qml` so QML re-evaluates them when `settings`
  changes. All other tokens remain `readonly property`.
- `settings` is a global QML context property — the `settings ? ... : ...`
  guard handles the brief startup window before it is set.
- Any test that asserts `Config` fields or `SettingsManager` properties must
  be updated if it checks the `ui` section of the saved JSON. Check
  `tests/test_config.py` and `tests/test_settings_manager.py` for any
  assertions on the `ui` dict keys and add `accent_color` / `focus_ring_color`
  where needed.
- Do not change any other QML file in this task — Theme token changes
  propagate automatically via bindings.
