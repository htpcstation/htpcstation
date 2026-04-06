# Task 002 — QML: per-row hotkey capture + rewind rows

## Context

Task 001 updated the backend. `settings.getRetroarchHotkeyConfig()` now returns:

```js
{
  modifier_evdev,      // int | null
  modifier_sdl,        // int | null
  modifier_label,      // str  e.g. "Home"
  mapping,             // dict hotkey_action → SDL index | null
  hotkey_rows,         // list of { hotkey_action, label, sdl_index, button_label }
  cfg_path,            // str
  rewind_enable,       // bool
  rewind_buffer_size,  // int (MB)
  rewind_granularity,  // int (frames)
}
```

`hotkey_rows` replaces the old `htpc_actions` key. Each row has:
- `hotkey_action` — e.g. `"save_state"`
- `label` — display string e.g. `"Save State"`
- `sdl_index` — int | null
- `button_label` — human-readable button name e.g. `"A/East"`, or `""` if not set

New slots available on `settings`:
- `settings.setHotkeyAction(hotkey_action: str, sdl_index: int)` — assign a button
- `settings.setRewindEnable(bool)`
- `settings.setRewindBufferSize(int)`
- `settings.setRewindGranularity(int)`

To clear a hotkey (set to null/nul), call `settings.setHotkeyAction(hotkey_action, -1)` — wait,
that won't work. See Constraints below for the correct clear approach.

Reference files (read before editing):
- `qml/screens/RetroarchHotkeysScreen.qml`
- `qml/screens/ModifierCaptureDialog.qml`

## Objective

1. Extend `ModifierCaptureDialog.qml` to support hold-to-clear (≥1s hold → emit `buttonCleared`).
2. Update `RetroarchHotkeysScreen.qml`:
   - Hotkey rows (1–10) become interactive — Accept opens the capture dialog.
   - Capture dialog result: assign or clear the row.
   - Add 3 rewind rows below the hotkey rows (before the Apply button): Rewind Enable (toggle), Buffer Size (left/right cycle), Rewind Frames (left/right cycle).
   - `_rowCount` and `_focusedRow` logic updated to cover all rows.

## Scope

### `qml/screens/ModifierCaptureDialog.qml`

**New signal:** `signal buttonCleared()`

**Hold-to-clear mechanic:**
- On `rawInput` with `evType === "button" && value === 1`: start a 1-second hold timer, record the button code.
- On `rawInput` with `evType === "button" && value === 0` (release): if hold timer has NOT fired, treat as a press → `_capture(code)`. If hold timer HAS fired, do nothing (already cleared).
- Hold timer fires after 1000ms: call `_clear()` which stops raw mode, hides dialog, emits `buttonCleared()`.
- Cancel (Escape / timeout) path unchanged.

**Updated instruction text:**
```
Press a button to assign.
Hold a button (1 second) to clear.
```

**Implementation notes:**
- Add a `property int _pendingCode: -1` to track the button being held.
- Add a `Timer { id: holdTimer; interval: 1000; repeat: false }`.
- On button-down: set `_pendingCode = code`, start `holdTimer`.
- On button-up: if `_pendingCode === code` and `holdTimer.running`, stop timer, call `_capture(code)`. Reset `_pendingCode = -1`.
- On `holdTimer.onTriggered`: call `_clear()`, reset `_pendingCode = -1`.
- `_clear()` function: same as `_cancel()` but emits `buttonCleared()` instead of `cancelled()`.
- The existing `_capture()` function is unchanged.
- Keep the existing `cancelled()` signal and `_cancel()` function unchanged.

### `qml/screens/RetroarchHotkeysScreen.qml`

**Row structure (total rows):**
- Row 0: modifier (existing)
- Rows 1–10: hotkey rows (from `config.hotkey_rows`)
- Row 11: Rewind Enable (toggle)
- Row 12: Buffer Size (left/right cycle)
- Row 13: Rewind Frames (left/right cycle)
- Row 14: Apply button

Update `_rowCount` accordingly:
```js
property int _rowCount: {
    var rows = (config && config.hotkey_rows) ? config.hotkey_rows.length : 0
    return 1 + rows + 3 + 1  // modifier + hotkeys + rewind rows + apply
}
```

**Hotkey rows (rows 1–10) — interactive:**

In `_activateFocused()`, rows 1–10 now open the capture dialog:
```js
} else if (hotkeysScreen._focusedRow >= 1 && hotkeysScreen._focusedRow <= rows) {
    var rowData = config.hotkey_rows[hotkeysScreen._focusedRow - 1]
    hotkeysScreen._captureTargetAction = rowData.hotkey_action
    hotkeyCaptureDialog.visible = true
    hotkeyCaptureDialog.forceActiveFocus()
}
```

Add `property string _captureTargetAction: ""` to track which row is being edited.

**Hotkey capture dialog wiring:**

The existing `modifierCaptureDialog` is for the modifier row only. Add a second instance of
`ModifierCaptureDialog` for hotkey rows:

```qml
ModifierCaptureDialog {
    id: hotkeyCaptureDialog
    anchors.fill: parent
    visible: false

    onButtonCaptured: (evdev_code) => {
        if (settings && hotkeysScreen._captureTargetAction !== "") {
            var sdl = settings.evdevToSdl(hotkeysScreen._captureTargetAction, evdev_code)
            // Actually: use the existing evdev→SDL lookup
        }
        hotkeysList.forceActiveFocus()
    }

    onButtonCleared: {
        if (settings && hotkeysScreen._captureTargetAction !== "") {
            settings.clearHotkeyAction(hotkeysScreen._captureTargetAction)
            hotkeysScreen.config = settings.getRetroarchHotkeyConfig()
        }
        hotkeysList.forceActiveFocus()
    }

    onCancelled: {
        hotkeysList.forceActiveFocus()
    }
}
```

Wait — `settings.evdevToSdl()` doesn't exist as a QML slot. The evdev→SDL conversion happens
in the backend. Use `settings.setHotkeyActionByEvdev(hotkey_action, evdev_code)` — but that
doesn't exist either.

**Correct approach:** Add a new slot to `settings_manager.py`:

```python
@Slot(str, int)
def setHotkeyActionByEvdev(self, hotkey_action: str, evdev_code: int) -> None:
    """Set a hotkey action by evdev code. Converts to SDL index internally."""
    sdl = _ra_cfg.evdev_code_to_sdl_index(evdev_code)
    mapping = dict(self._config.hotkey_mapping)
    mapping[hotkey_action] = sdl  # None if unknown evdev code
    self._config.set_hotkey_mapping(mapping)
```

And a clear slot:

```python
@Slot(str)
def clearHotkeyAction(self, hotkey_action: str) -> None:
    """Clear a single hotkey action (set to None/nul)."""
    mapping = dict(self._config.hotkey_mapping)
    mapping[hotkey_action] = None
    self._config.set_hotkey_mapping(mapping)
```

Add both to `settings_manager.py` in this task (small backend addition, needed for QML wiring).

Then in QML:
```qml
onButtonCaptured: (evdev_code) => {
    if (settings && hotkeysScreen._captureTargetAction !== "") {
        settings.setHotkeyActionByEvdev(hotkeysScreen._captureTargetAction, evdev_code)
        hotkeysScreen.config = settings.getRetroarchHotkeyConfig()
    }
    hotkeysList.forceActiveFocus()
}

onButtonCleared: {
    if (settings && hotkeysScreen._captureTargetAction !== "") {
        settings.clearHotkeyAction(hotkeysScreen._captureTargetAction)
        hotkeysScreen.config = settings.getRetroarchHotkeyConfig()
    }
    hotkeysList.forceActiveFocus()
}
```

**Hotkey row display (delegate update):**

The existing delegate already has a `_isModifier` branch and a hotkey branch. Update the hotkey
branch to use `hotkey_rows` instead of `htpc_actions`:

- Left column: `modelData._data.label` (e.g. "Save State")
- Right column: `modelData._data.button_label || "Not set"` — color it `Theme.colorPrimary` if
  set, `Theme.colorTextDim` if not set.
- Remove the `_isDimmed` logic (all rows are now equally interactive).
- Add a small "▶" or "..." hint on the focused row to indicate it's interactive (optional — use
  the existing focus ring as the affordance if you prefer to keep it simple).

**ListView model update:**

The model currently builds from `htpc_actions`. Update to use `hotkey_rows`:
```js
model: {
    var rows = [{ _type: "modifier" }]
    var hotkeys = (hotkeysScreen.config && hotkeysScreen.config.hotkey_rows)
        ? hotkeysScreen.config.hotkey_rows : []
    for (var i = 0; i < hotkeys.length; i++) {
        rows.push({ _type: "hotkey", _data: hotkeys[i] })
    }
    return rows
}
```

**Rewind rows (rows 11–13):**

These live OUTSIDE the `ListView` (same as the Apply button), stacked between the list bottom
and the Apply button. Use three `Item` rows of height `vpx(56)` each, anchored below the list.

Adjust `hotkeysList` bottom anchor: `bottom: rewindSection.top` instead of `bottom: applyButton.top`.

Add a `Column` or three stacked `Item`s for the rewind rows:

```qml
Item {
    id: rewindSection
    anchors {
        left: parent.left; right: parent.right
        bottom: applyButton.top
        leftMargin: vpx(48); rightMargin: vpx(48)
        bottomMargin: vpx(0)
    }
    height: vpx(56) * 3

    // Row 11: Rewind Enable (toggle)
    // Row 12: Buffer Size (cycle: 20,40,60,80,100,150,200,300,500)
    // Row 13: Rewind Frames (cycle: 1,2,4,8,16,32)
}
```

For each rewind row:
- Show focus ring when `hotkeysScreen._focusedRow === <row_index>`.
- **Rewind Enable (row 11):** Left column label "Rewind", right column shows "On" / "Off".
  Accept toggles it: `settings.setRewindEnable(!hotkeysScreen._rewindEnable)` then refresh
  `_rewindEnable` from config.
- **Buffer Size (row 12):** Left column "Buffer Size", right column shows current value + " MB".
  Left/Right keys cycle through `[20, 40, 60, 80, 100, 150, 200, 300, 500]`.
  Call `settings.setRewindBufferSize(newValue)` on change.
- **Rewind Frames (row 13):** Left column "Rewind Frames", right column shows current value + " frames".
  Left/Right keys cycle through `[1, 2, 4, 8, 16, 32]`.
  Call `settings.setRewindGranularity(newValue)` on change.

Add internal state properties:
```js
property bool _rewindEnable: config ? config.rewind_enable : false
property int _rewindBufferSize: config ? config.rewind_buffer_size : 20
property int _rewindGranularity: config ? config.rewind_granularity : 1
```

These update when `config` is refreshed (after capture dialog closes).

**Key handling for rewind rows:**

In `Keys.onPressed`, add handling for Left/Right when focused on rows 12 or 13:
```js
} else if (event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
    event.accepted = true
    _handleRewindCycle(event.key)
}
```

`_activateFocused()` for row 11 (toggle):
```js
} else if (hotkeysScreen._focusedRow === rows + 1 + 1) {  // row 11 = modifier(1) + hotkeys(10) + 1
    // toggle rewind enable
}
```

Use concrete index arithmetic based on `_rowCount` definition to avoid off-by-one errors.
Define named constants or compute inline — be explicit.

**`_scrollToFocused()` update:**

The rewind rows and apply button are outside the ListView. Only scroll for rows 0 through
`hotkey_rows.length` (inclusive of modifier). For rows beyond that, no scroll needed.

**Apply button row index:**

Was `actions + 1`. Now `1 + hotkey_rows.length + 3 + 0` = row 14 (0-indexed).
Update `applyButton._isFocused` binding accordingly.

## Non-goals / Later

- Do NOT add per-system override UI.
- Do NOT change `SettingsScreen.qml` — the "RetroArch Hotkeys" button already opens this screen.
- Do NOT add Q_PROPERTYs for rewind in `settings_manager.py` (not needed — read via `getRetroarchHotkeyConfig()`).

## Constraints / Caveats

- **Never use `id: root`** — ApplicationWindow owns that id. Use `hotkeysScreen` or `rewindSection` etc.
- **Only ONE `Component.onCompleted` per QML scope** — the existing one resets `_focusedRow = 0`. Don't add a second.
- **`enabled: focus`** on the FocusScope — the rewind rows and capture dialog must not steal focus unexpectedly.
- The two `ModifierCaptureDialog` instances (`modifierCaptureDialog` and `hotkeyCaptureDialog`) are both declared at the bottom of the file so they render on top. Both use `anchors.fill: parent`.
- After any dialog closes, focus must return to `hotkeysList` (existing pattern — already done for modifier dialog, replicate for hotkey dialog).
- `hotkeysScreen.config` is refreshed by calling `settings.getRetroarchHotkeyConfig()` after each assignment/clear. This is the same pattern as the modifier row.
- The `_rewindEnable`, `_rewindBufferSize`, `_rewindGranularity` properties should update reactively when `config` changes. Use `onConfigChanged` handler or bind directly to `config.rewind_*` fields.
- Rewind rows use Left/Right to cycle AND Accept to activate (for the toggle). The cycle rows (12, 13) should also respond to Accept by cycling forward (same as Left Shoulder / Right Shoulder pattern in `SystemCoresScreen`).

## Acceptance criteria

- Pressing Accept on any of the 10 hotkey rows opens the capture dialog.
- Pressing a button in the dialog assigns it; holding ≥1s clears the row (shows "Not set").
- The 3 rewind rows are visible, navigable, and their values persist (written to config on change, written to retroarch.cfg on Apply).
- Apply button writes all hotkeys + rewind to retroarch.cfg (existing backend behavior — no QML change needed for the write itself).
- Focus returns to the list after any dialog closes.
