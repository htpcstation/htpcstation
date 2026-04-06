# HTPC Station — Resume Document (Checkpoint 32)

> Hand this file to a fresh agent to resume development.
> Deep reference (architecture, full gotchas, gamepad controls): `docs/architecture.md`
> Roadmap and milestone specs: `docs/milestones.md`
> Checkpoint history and task brief archive: `docs/changelog.md`

---

## Documentation Maintenance

**Keep these docs current as you work. Update before committing.**

| Doc | Update when |
|---|---|
| `resume-project.md` | Every checkpoint: bump number, update state/test count, revise next milestone |
| `architecture.md` | Any structural change: new file, renamed signal, removed method, new gotcha discovered |
| `milestones.md` | Milestone completed (mark ✅ + note what actually shipped vs plan), new milestone added |
| `changelog.md` | Every checkpoint: one-line entry + task brief directory reference |

---

## Current State

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. **1,910 tests passing.**

**Tabs (in order):** Retro Games | PC Games | Moonlight | Plex Media | Plex Music | Settings

**What's new since CP31:**
- M6→V2: RetroArch hotkey config V2. All 12 hotkey rows interactive (tap to assign, hold 3s to clear). Rewind settings (enable/buffer/granularity). Duplicate button prevention. Hotkeys: Save/Load State, Fast Forward (Toggle/Hold), Rewind, Open Menu, Screenshot, Show FPS, Next/Prev Save Slot, Pause Toggle, Exit Emulator.
- M8-A: `backend/sdl_resolver.py` — ctypes SDL wrapper, probes libSDL2/libSDL3 at import, resolves evdev events to SDL records via GameControllerDB. Works on any distro.
- M8-B: Dual-record controller mapping. Every entry stores `evdev` half (Qt key injection) and `sdl` half (RetroArch cfg, browser extension). Co-firing event collection for dual-reporting devices (D-input triggers). `saveControllerMapping` resolves SDL records at save time (before `stopRawMode`).
- M8-C: Dual-record hotkey assignment. `HOTKEY_CFG_KEYS` triple keys per action (`_btn`/`_axis`/`_hat`). `build_hotkey_cfg` writes correct key type. `ModifierCaptureDialog` handles buttons, axes, hats. Face button labels honour standard/alternate layout with cardinal positions (e.g. "A (East)", "X (North)").
- M8-D: Controller mapping wizard improvements: Start+Select cancel, cancel hint adapts to gamepad/keyboard, `getControllerActionEvdevCodes` slot. Hold-to-skip WIP (records immediately on press for dual-reporting triggers — fix pending).

**Known issue (fix next session):** Hold-to-skip in controller mapping wizard records immediately on press for dual-reporting inputs (triggers fire axis event first, which starts hold timer, then button event hits `else` branch and calls `_recordInput`). Fix: button events when `_holdSkipCode !== -1` should be ignored.

**Next milestone:** M7 — Local Music tab V1. See `docs/milestones.md`.

---

## Stack

| | |
|---|---|
| Framework | Qt 6 / QML + PySide6 (Python 3.10+) |
| Target | Linux x86_64, Xorg or Wayland, Intel J5005-class or better |
| Video playback | libmpv in-process via python-mpv, VA-API hwdec, direct Plex stream URLs (transient token) |
| Live TV | HDHomeRun direct streams + SiliconDust guide API (`api.hdhomerun.com`) |
| Emulator | RetroArch via Flatpak |
| PC games | Steam URI (`steam://rungameid/`), Moonlight CLI (Flatpak) |
| Plex music | Qt MediaPlayer + AudioOutput (direct Plex audio streams) |
| Browser | Brave Flatpak (music playback, MPV fallback) |
| Gamepad | evdev → synthetic QKeyEvent injection |
| Config | `~/.config/htpcstation/config.json` |
| MPV config | No `input.conf` — bindings registered via `player.keybind()` at startup |
| Live TV cache | `~/.config/htpcstation/livetv_cache/guide_cache.json` |
| Poster cache | `~/.config/htpcstation/poster_cache/{sha256}.jpg` |

---

## Commands

```bash
python3 main.py           # run directly
./htpcstation.sh          # run via launcher (after install.sh)
python3 -m pytest tests/ -q
bash scripts/check-deps.sh
bash install.sh
```

---

## QML Context Properties

| Name | Type | Purpose |
|---|---|---|
| `keys` | Keys | Semantic key checks, input source, button layout labels |
| `library` | GameLibrary | ROM data, models, launch, favorites |
| `steam` | SteamLibrary | Steam games, models, sort, launch, favorites, recently played |
| `moonlight` | MoonlightLibrary | Moonlight host/app data, models, launch, favorites, recently played |
| `plex` | PlexLibrary | Plex data, models, sort/filter, MPV/browser launch, My List, subtitle IPC, timeline reporting, track persistence, markers, SSE listener |
| `liveTV` | LiveTvLibrary | HDHomeRun guide + streams, MPV launch, guide cache |
| `gamepadManager` | GamepadManager | Raw mode for mapping dialog, device capabilities |
| `networkMonitor` | NetworkMonitor | Periodic connectivity check |
| `settings` | SettingsManager | Config read/write for settings UI, OAuth, PIN login |

---

## Critical Gotchas

The full catalogue is in `docs/architecture.md`. These are the ones most likely to bite first:

**Never use `id: root` in any QML component.** That id belongs to the ApplicationWindow where `vpx()` is defined.

**QML context properties are null on first render.** Guard all bindings: `plex ? plex.model : null`.

**Never name a signal `<propertyName>Changed`.** QML auto-generates those — naming conflict makes the component type "unavailable" with no useful error.

**Only ONE `Component.onCompleted` per QML scope.** QML silently ignores the second one.

**HomeScreen tab array must be built imperatively in `Component.onCompleted`.** Never bind it to `settings.*` — causes cascading focus destruction and app freeze.

**`Loader` recreates the screen on every tab switch.** Trigger data loads in `Component.onCompleted`, not just `onActiveFocusChanged` — focus is only given when the user presses Down from the tab bar.

**python-mpv callbacks run on the mpv event thread.** Never call Qt UI methods directly — use `QMetaObject.invokeMethod` with `QueuedConnection`.

**`_mpvLaunchReady` signal carries 6 args:** `(url, title, start_ms, duration_ms, part_id, intro_end_ms)`. All test mocks must match this signature.

**`Config.save()` refuses to write if in-memory token+server_id are blank but the on-disk file has credentials.** This guard prevents config wipes from rogue `Config()` instantiations. Never construct a second `Config()` instance — pass the existing one.

**`MoonlightScreen` view mode:** child components call `settings.setPcGamesViewMode()` directly. `MoonlightScreen.on_ViewModeChanged` overrides this with `settings.setMoonlightViewMode()`.

---

## Dev Machine

- ThinkPad T480, i5-8350U, Intel UHD 620, Fedora 43, Wayland (GNOME/Mutter)
- ROMs: `~/opencode/ROMs/` (gb, ngpc, sega32x)
- Steam: Flatpak, 5 games
- Moonlight: Flatpak, 1 paired host, 7 apps
- Plex: local server + HDHomeRun FLEX 4K tuner at `192.168.0.2`
- Controller: 8BitDo Micro in D-input mode (Bluetooth)
- HDHomeRun DeviceAuth: in `discover.json` at `http://192.168.0.2/discover.json`
