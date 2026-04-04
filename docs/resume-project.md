# HTPC Station — Resume Document (Checkpoint 21)

> Hand this file to a fresh agent to resume development.
> For full codebase structure, gotchas, architecture notes, and history: `docs/architecture.md`

---

## Current State

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. All 5 tabs working: Retro Games, PC Games, Watch, Listen, Settings. **1,532 tests passing.**

**What's new since Checkpoint 20:**

Post-libmpv migration bugfixes — all squashed into one commit on top of checkpoint 20:
- `fullscreen=yes` restored in `mpv.MPV()` kwargs (required for in-window rendering)
- `start='none'` used to clear resume position (empty string caused seek+pause on some streams)
- `is_running()` now checks `player.filename` (not process state)
- `input_default_bindings=True` + `input_vo_keyboard=True` needed for keyboard input in MPV
- `LC_NUMERIC=C` set immediately before `mpv.MPV()` creation (Qt resets the locale)
- Keybinds: `GAMEPAD_ACTION_LEFT=X=show-progress`, `GAMEPAD_ACTION_UP=Y=osd-msg cycle sub`
- `stop` used instead of `quit` in all keybinds — keeps the libmpv core alive for reuse
- `_emit_started` guarded: only fires if `wait_until_playing()` succeeds (not on stop/timeout)
- Subtitle picker overlay removed entirely — Y button now triggers `osd-msg cycle sub` (MPV native)
- `MpvSubtitleOverlay.qml` deleted
- Gamepad input suppressed in Qt while MPV is active (prevents double-input); restored on stop
- L2/R2 keybinds: tried `keybind {no-repeat}` → `on_key_press` → `key_binding` with state=='p' + `command_async` — **ultimately disabled** (feature removed; dpad scrobbling is sufficient)
- `pause=False` set before `player.play()` in both `launch()` and `launch_live_tv()` — fixes MPV starting in a paused state

---

## Roadmap

| # | Item | Notes |
|---|---|---|
| 1 | ~~F3 — PC Games Favorites~~ | ✅ Done |
| 2 | ~~C2 — System Cores settings~~ | ✅ Done |
| 3 | Moonlight rich metadata | Deferred — nearly free when resumed (`steam_app_id` already in `artwork_index.json`) |
| 4 | ~~F4 — Plex My List~~ | ✅ Done |
| 5 | ~~UI Refresh 4a — token interface + Theme.qml palettes~~ | ✅ Done |
| 6 | On-screen keyboard | Needed for gamepad-only wizard text input |
| 7 | X1 — First-run setup wizard | Built on new tokens + OSK |
| 8 | UI Refresh 4b/4c — QML token replacement + theme switcher | High blast radius, phase separately |
| 9 | Listen tab enhancements | Shuffle/repeat, seek bar, volume |
| 10 | ~~Mark watched/unwatched (Plex)~~ | ✅ Done — Y button on detail screens |
| 11 | Plex search | New navigation flow |
| 12 | Custom user-defined collections | Needs scoping |
| 13 | GOG/Epic Games Store | Needs spike first |
| 14 | Standalone emulator support (Dolphin, PCSX2) | Additive launcher extension |
| 15 | Gamepad extension: YouTube/Netflix | Browser extension work |
| 16 | ~~`/hubs/home/continueWatching` swap~~ | ✅ Done |
| 17 | ~~Typed error handling + retry (`PlexError` enum)~~ | ✅ Done |
| 18 | ~~Plex play queue (`POST /playQueues`)~~ | ✅ Done |
| 19 | ~~`X-Plex-Client-Profile-Extra` header~~ | ✅ Done |
| 20 | ~~Playback history (`GET /status/sessions/history/all`)~~ | ✅ Done |
| 21 | ~~Self-healing server connection~~ | ✅ Done |
| 22 | ~~Server events SSE (`/:/eventsource/notifications`)~~ | ✅ Done |
| 23 | ~~Rating (`PUT /:/rate`)~~ | ✅ Done — backend only; UI binding deferred (no free face button) |
| 24 | ~~Focus memory per row (WatchScreen)~~ | ✅ Done |
| 25 | Hero/header fade on content focus | Deferred — UI polish |
| 26 | ~~In-app Plex login~~ | ✅ Done — PIN overlay in Settings |
| 27 | Plex search | UI — new navigation flow |
| 28 | ~~libmpv migration (python-mpv) — tasks 001–003~~ | ✅ Done — `LibMpvPlayer` (python-mpv), programmatic keybinds, push-based timeline reporter (no IPC polling). `MpvIpc` deleted. |
| 29 | Rating UI — thumbs up/down on detail screen | Needs a free button; deferred |
| 30 | Custom user-defined collections | Needs scoping |
| 31 | GOG/Epic Games Store | Needs spike first |
| 32 | Standalone emulator support (Dolphin, PCSX2) | Additive launcher extension |
| 33 | Gamepad extension: YouTube/Netflix | Browser extension work |
| 34 | Plex token encryption / OS keyring | Security hardening |
| 35 | Moonlight rich metadata | Deferred |

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
# Run
python3 main.py

# Test
python3 -m pytest tests/ -q

# Check dependencies
bash scripts/check-deps.sh
```

---

## QML Context Properties

| Name | Type | Purpose |
|---|---|---|
| `keys` | Keys | Semantic key checks, input source, button layout labels |
| `library` | GameLibrary | ROM data, models, launch, favorites |
| `steam` | SteamLibrary | Steam/Moonlight games, models, sort, launch, favorites |
| `moonlight` | MoonlightLibrary | Moonlight host/app data, models, launch |
| `plex` | PlexLibrary | Plex data, models, sort/filter, MPV/browser launch, My List, subtitle IPC, timeline reporting, track persistence, markers, SSE listener |
| `liveTV` | LiveTvLibrary | HDHomeRun guide + streams, MPV launch, guide cache |
| `gamepadManager` | GamepadManager | Raw mode for mapping dialog, device capabilities |
| `networkMonitor` | NetworkMonitor | Periodic connectivity check |
| `settings` | SettingsManager | Config read/write for settings UI, OAuth, PIN login |

---

## Critical Gotchas (read before touching these areas)

**QML context properties are null on first render.** Guard all bindings: `plex ? plex.model : null`. Applies to `liveTV`, `steam`, `settings`, etc.

**Never use `id: root` in any QML component.** That id belongs to the ApplicationWindow where `vpx()` is defined.

**Never name a signal `<propertyName>Changed`.** QML auto-generates those and the conflict makes the component type "unavailable".

**HomeScreen tab arrays must be built imperatively, not via bindings.** Binding to `settings.showRetroGamesTab` causes cascading focus destruction and freezes the app. Build in `Component.onCompleted` only.

**Only ONE `Component.onCompleted` per QML scope.** QML silently fails with "Property value set multiple times" if you have two.

**Plex managed user tokens get 401 from the media server.** Always use the admin token for server API calls. User token is only for browser deep links.

**MPV on Wayland needs `hwdec=vaapi-copy` and `gpu_context=wayland`.** On Xorg use `hwdec=vaapi` and `gpu_context=x11`. `LibMpvPlayer._gpu_context()` and `_hwdec_mode()` auto-detect from `XDG_SESSION_TYPE`. These are passed as kwargs to `mpv.MPV()`, not as CLI flags.

**Fedora ships codec-restricted packages.** `ffmpeg-free` → swap for `ffmpeg` (RPM Fusion). `libva-intel-media-driver` → swap for `libva-intel-driver` (RPM Fusion). `check-deps.sh` detects and reports these.

**`flatpak kill <app_id>` required to close Brave.** `QProcess.kill()` only kills the wrapper, not the sandboxed browser.

**Moonlight QSettings INI fields are all lowercase.** `hostname`, `localaddress`, `uuid` — not camelCase.

**Theme.qml: use semantic tokens, never `_palette` vars.** `_bg`, `_accent`, etc. are internal. QML files reference `colorBackground`, `colorAccent`, etc. `colorPrimary` and `colorSecondary` are kept as aliases for the 255 existing usages — rename them in 4b/4c.

**`PlexOnDeckGrid` and `PlexOnDeckList` expose `currentIndex` as a writable property** (not readonly). Writing to it from WatchScreen sets `_suppressIndexReset = true` first to prevent the `onActiveFocusChanged` handler from resetting to 0.

**`PlexTimelineReporter` uses a daemon thread.** Started in `_on_mpv_started_for_timeline`, stopped in `_on_mpv_finished_for_timeline`. `PlexLibrary.shutdown()` also calls `stop()`. Position updated via push-based `@property_observer('time-pos')` registered in `PlexLibrary.set_wid()` — no IPC polling.

**`_mpvLaunchReady` signal carries 5 args** `(url, title, start_ms, duration_ms, part_id)`. All test mocks must match this signature.

**HDHomeRun guide API uses `DeviceAuth` token** from `http://{host}/discover.json`, not the Plex token. The guide endpoint is `https://api.hdhomerun.com/api/guide?DeviceAuth={token}`. The Plex cloud EPG grid endpoint (`/{epg_key}/grid`) ignores `channelGridKey` filter — do not use it for per-channel data.

**Plex EPG timestamps are unreliable** (may be ~1 year ahead of wall clock). Use HDHomeRun guide timestamps instead — they are accurate Unix seconds.

**MPV gamepad key names are SDL positional, not label-based.** On the 8BitDo Micro in D-input mode (Bluetooth), verified with `mpv --input-test`: A (east, evdev 304) = `GAMEPAD_ACTION_DOWN`, B (south, evdev 305) = `GAMEPAD_ACTION_RIGHT`, Start = `GAMEPAD_START`. Dpad scrobbling uses `GAMEPAD_DPAD_LEFT/RIGHT` (seek ±10s). L2/R2 triggers are **not bound** — feature was removed after multiple failed attempts (keybind `{no-repeat}`, `on_key_press`, `key_binding` state=='p' + `command_async` all had issues); dpad is sufficient.

**`SDL_GAMECONTROLLERCONFIG` override has no effect on this device.** The 8BitDo Micro's SDL mapping is already correct in the system database. Do not attempt to override it.

**python-mpv callbacks run on the mpv event thread.** Never call Qt UI methods directly from a property observer or `on_key_press` callback. Always use `QMetaObject.invokeMethod` with `Qt.ConnectionType.QueuedConnection`.

**`LibMpvPlayer.set_wid()` must be called after `window.showFullScreen()`.** `winId()` is only valid after the window is mapped. In `main.py`, call `plex_library.set_wid(int(window.winId()))` after `showFullScreen()`.

**`LibMpvPlayer.launch()` sets `pause=False` before `play()`.** MPV can retain a paused state across loads. This must stay — removing it will cause MPV to start paused intermittently.

---

## Dev Machine

- ThinkPad T480, i5-8350U (Kaby Lake-R), Intel UHD 620, Fedora 43, Wayland
- ROMs: `~/opencode/ROMs/` (gb, ngpc, sega32x)
- Steam: Flatpak, 5 games
- Moonlight: Flatpak, 1 paired host, 7 apps
- Plex: local server + HDHomeRun FLEX 4K tuner at `192.168.0.80`
- Controller: 8BitDo Micro in D-input mode (Bluetooth; D-pad as ABS_HAT0X/Y hat axes; face buttons BTN_SOUTH/EAST/NORTH/WEST; triggers BTN_TL2/TR2 + ABS_BRAKE/GAS axes)
- HDHomeRun DeviceAuth: in `discover.json` at `http://192.168.0.80/discover.json`
