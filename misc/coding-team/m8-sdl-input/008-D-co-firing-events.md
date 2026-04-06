# Task 008-D — Record co-firing events in controller mapping wizard

## Context

Dual-reporting devices (e.g. 8BitDo Micro in D-input mode) fire both an EV_ABS axis event
AND an EV_KEY button event when a trigger is pressed. The wizard currently records only the
primary event per action. This means the axis event (e.g. ABS_GAS, code 9) is never stored
in the mapping, so `seed_from_controller_mapping` cannot populate `_evdev_event_to_sdl` for
it. When the hotkey capture dialog receives the axis event first, it falls through to the GC
heuristic and gets a wrong label ("Axis 4+").

The fix: record ALL events that fire within the same tick for each action. Store them as
`also: [{type, code, value}, ...]` on the entry. `saveControllerMapping` resolves SDL records
for both the primary and `also` events. `seed_from_controller_mapping` populates
`_evdev_event_to_sdl` for all of them, pointing to the same SDL record.

## Scope

### `qml/screens/ControllerMappingDialog.qml`

**Replace the `_pendingAxis` / `pendingAxisTimer` approach** with a co-firing collector:

- Add `property var _coFiringEvents: []` — accumulates all events that arrive in the same
  tick as the primary event.
- Add `Timer { id: coFiringTimer; interval: 0; repeat: false }` — fires one tick after the
  primary event is recorded, at which point `_coFiringEvents` is complete.

**New `_onRawInput` flow:**

```qml
function _onRawInput(evType, code, value) {
    if (mappingDialog._state !== "waiting") return
    if (evType === "button" && value !== 1) return
    if (_isDuplicate(evType, code, value)) {
        _statusText = "Already mapped — press a different button"
        return
    }

    if (!coFiringTimer.running) {
        // First event for this action — record it as primary and start collector
        mappingDialog._coFiringEvents = []
        _recordInput(evType, code, value)
        coFiringTimer.restart()
    } else {
        // Co-firing event — add to the list (don't advance, don't change state)
        mappingDialog._coFiringEvents.push({"type": evType, "code": code, "value": value})
    }
}
```

**`coFiringTimer.onTriggered`:**
```qml
onTriggered: {
    // Co-firing collection window closed. If any co-firing events were collected,
    // update the last recorded entry to include them.
    if (mappingDialog._coFiringEvents.length > 0) {
        var last = _recordedMappings[_recordedMappings.length - 1]
        last.also = mappingDialog._coFiringEvents.slice()
        _recordedMappings[_recordedMappings.length - 1] = last
        mappingDialog._coFiringEvents = []
    }
}
```

**`_recordInput`** — unchanged. It sets `_state = "recorded"` which disables the `Connections`
block for subsequent events. But `coFiringTimer` is already running, so co-firing events that
arrive before the binding re-evaluates are caught by the `!coFiringTimer.running` check in
`_onRawInput` — they go into `_coFiringEvents`.

Wait — `_state = "recorded"` disables `Connections` (`enabled: _state === "waiting"`). The
co-firing events arrive in the same tick before the binding re-evaluates, so they DO reach
`_onRawInput`. The `if (mappingDialog._state !== "waiting") return` guard at the top would
block them. 

**Fix:** move the `_state !== "waiting"` guard to only apply when `coFiringTimer` is NOT
running:

```qml
function _onRawInput(evType, code, value) {
    // Allow co-firing events through even after state changes to "recorded",
    // as long as the co-firing collection window is open.
    if (mappingDialog._state !== "waiting" && !coFiringTimer.running) return
    if (evType === "button" && value !== 1) return
    if (_isDuplicate(evType, code, value)) return  // silently skip duplicates during co-firing

    if (!coFiringTimer.running) {
        // First event — record as primary
        mappingDialog._coFiringEvents = []
        _recordInput(evType, code, value)
        coFiringTimer.restart()
    } else {
        // Co-firing event — collect it
        mappingDialog._coFiringEvents.push({"type": evType, "code": code, "value": value})
    }
}
```

**Remove** `_pendingAxis`, `pendingAxisTimer`, and all references to them.

**`_cancel`** — add `coFiringTimer.stop()` and `mappingDialog._coFiringEvents = []`.

**`_isDuplicate`** — also check `also` arrays of existing entries:
```qml
function _isDuplicate(evType, code, value) {
    for (var i = 0; i < _recordedMappings.length; i++) {
        var m = _recordedMappings[i]
        if (m.type === evType && m.code === code && m.value === value) return true
        var also = m.also || []
        for (var j = 0; j < also.length; j++) {
            if (also[j].type === evType && also[j].code === code && also[j].value === value)
                return true
        }
    }
    return false
}
```

### `backend/settings_manager.py` — `saveControllerMapping`

For each entry, after resolving the primary SDL record, also resolve each `also` event:

```python
also_raw = entry.get("also") or []
also_evdev: list[dict] = []
for ae in also_raw:
    ae_type = ae.get("type")
    ae_code = ae.get("code")
    ae_value = ae.get("value")
    if ae_type in ("button", "axis") and isinstance(ae_code, int) and isinstance(ae_value, int):
        ae_evdev = {"type": ae_type, "code": ae_code, "value": ae_value}
        ae_sdl = _sdl_resolver.resolve(ae_type, ae_code, ae_value)
        also_evdev.append({"evdev": ae_evdev, "sdl": ae_sdl})

mapping_dict[name] = {
    "evdev": evdev_part,
    "sdl": sdl_part,
    "also": also_evdev,   # list of {"evdev": {...}, "sdl": {...}}
}
```

`also` is omitted (empty list) for actions with no co-firing events. `load_mapping` already
handles unknown keys gracefully (ignores them), so no migration needed.

### `backend/sdl_resolver.py` — `seed_from_controller_mapping`

After processing the primary entry, also process each `also` entry:

```python
# Primary entry
self._evdev_event_to_sdl[(evdev_type, evdev_code)] = sdl_record

# Co-firing entries — same SDL record
for also_entry in entry.get("also") or []:
    also_evdev = also_entry.get("evdev")
    also_sdl = also_entry.get("sdl")
    if not (isinstance(also_evdev, dict) and also_evdev.get("type") in ("button", "axis")
            and isinstance(also_evdev.get("code"), int)):
        continue
    also_type = also_evdev["type"]
    also_code = also_evdev["code"]
    if (also_type, also_code) in self._evdev_hat_to_sdl:
        continue
    # Use the also entry's own SDL record if available, otherwise use the primary
    if isinstance(also_sdl, dict) and also_sdl.get("type") in ("button", "axis", "hat"):
        also_record = _build_sdl_record(also_sdl, self._sdl_button_to_label)
    else:
        also_record = sdl_record  # fall back to primary SDL record
    self._evdev_event_to_sdl[(also_type, also_code)] = also_record
```

Extract the SDL record building logic into a helper `_build_sdl_record(sdl_part, button_labels)`
to avoid duplication between primary and also entries.

### `backend/controller_mapping.py` — `load_mapping`

Update validation to preserve the `also` field:

```python
result[action] = {
    "evdev": evdev_part,
    "sdl": sdl_part,
    "also": entry.get("also") or [],
}
```

### Tests

**`tests/test_controller_mapping.py`:**
- Add test: entry with `also` field is preserved through save/load round-trip.
- Add test: `_isDuplicate` checks `also` arrays (Python-side: verify `also` is stored).

**`tests/test_sdl_resolver.py` — `TestSdlResolverSeedFromControllerMapping`:**
- Add test: `also` entries are seeded into `_evdev_event_to_sdl`.
- Add test: `also` entry with its own SDL record uses that record, not the primary.
- Add test: `also` entry with null SDL falls back to primary SDL record.

**`tests/test_settings_backend.py`:**
- Update `saveControllerMapping` test: entry with `also` raw events produces `also` in saved dict.

## Non-goals / Later

- Do NOT change `ModifierCaptureDialog.qml` — the hotkey capture dialog doesn't need
  co-firing collection. Once `_evdev_event_to_sdl` is populated correctly from the wizard,
  the axis event will resolve to the correct SDL record via the mapping lookup.
- Do NOT change `RetroarchHotkeysScreen.qml`.
- Do NOT change `retroarch_config.py`.

## Constraints / Caveats

- The `coFiringTimer` (interval: 0) fires after the current event loop tick completes.
  All co-firing events from the same `_on_readable()` loop will have arrived by then.
- `_isDuplicate` during co-firing collection: silently skip (don't show "already mapped"
  message) since the user didn't press a different button — it's the same physical input.
- `also` entries in the saved JSON are `[{"evdev": {...}, "sdl": {...}}, ...]`. The `sdl`
  half of an `also` entry may differ from the primary (e.g. primary is button, also is axis
  with a different SDL record). Always resolve each independently.
- After all changes: `python3 -m pytest tests/ -q` must show 0 failures.
