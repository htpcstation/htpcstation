# Task 004 — Suppress gamepad injection for all external app launchers; rename setMpvActive

## Context

`GamepadManager.setMpvActive()` suppresses Qt key injection (and calls
`_release_all_keys()` on deactivation) while an external app owns the
gamepad. It was only wired to `plex_library.mpvStarted/mpvFinished`.

Three other launchers hide the Qt window while running but never suppress
the gamepad:
- `launcher` (RetroArch / emulators)
- `browser_launcher` (Plex Web kiosk)
- `moonlight` (game streaming)

During any of these sessions, D-pad/button events are still processed,
injected into the hidden Qt window, and auto-repeat timers can be left
running. If the user holds a direction at exit time, the repeat timer
keeps firing `Key_Down` (or any key) into the restored UI indefinitely —
causing the observed stuck-scroll bug.

The method name `setMpvActive` / field `_mpv_active` in `gamepad.py` is
misleading now that it covers all external apps.

Note: `_mpv_active` also exists in `plex_library.py` and
`live_tv_library.py` as an internal field — those are unrelated and must
NOT be renamed.

## Objective

1. Rename in `gamepad.py` only:
   - `setMpvActive` → `setExternalAppActive`
   - `_mpv_active` → `_external_active`

2. Wire `setExternalAppActive` to all four launchers in `main.py`:
   - `launcher.processStarted` → `setExternalAppActive(True)`
   - `launcher.processFinished` → `setExternalAppActive(False)`
   - `browser_launcher.processStarted` → `setExternalAppActive(True)`
   - `browser_launcher.processFinished` → `setExternalAppActive(False)`
   - `moonlight.processStarted` → `setExternalAppActive(True)`
   - `moonlight.processFinished` → `setExternalAppActive(False)`
   - Keep existing: `plex_library.mpvStarted/mpvFinished` → `setExternalAppActive(True/False)`

3. Update `docs/architecture.md`:
   - In the codebase structure entry for `gamepad.py` (line 27): replace
     `setMpvActive()` with `setExternalAppActive()`.
   - Add a new gotcha entry to the `### Gamepad` section (after the last
     existing bullet, before `### Other`):

```
- **All external app launchers must call `setExternalAppActive()`** —
  `GamepadManager` suppresses Qt key injection and clears all held-key
  state when an external app is active. Any launcher that hides the Qt
  window (emulators, browser kiosk, Moonlight, MPV) must call
  `setExternalAppActive(True)` on start and `setExternalAppActive(False)`
  on finish. Omitting this leaves auto-repeat timers running into the
  restored UI — manifests as a grid/list that scrolls to the bottom and
  ignores Up input until the gamepad is disconnected.
```

## Scope

- `backend/gamepad.py` — rename `setMpvActive` → `setExternalAppActive`,
  `_mpv_active` → `_external_active`. Update the docstring on the method.
- `main.py` — add 6 new signal connections; update the 2 existing lambda
  call-sites to use the new name.
- `docs/architecture.md` — two edits as described above.

## Non-goals / Later

- Do not rename `_mpv_active` in `plex_library.py` or `live_tv_library.py`.
- Do not change any QML.
- Do not change the `@Slot` decorator (signature is unchanged: `bool`).

## Constraints / Caveats

- `launcher.processFinished` carries `(int, int)` args — use a lambda:
  `lambda *_: gamepad_manager.setExternalAppActive(False)` (same pattern
  as the existing MPV wiring).
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
  Any test that references `setMpvActive` or `_mpv_active` on
  `GamepadManager` must be updated to the new name.
