# HTPC Station — Resume Document (Checkpoint 19)

> Hand this file to a fresh agent to resume development.
> For full codebase structure, gotchas, architecture notes, and history: `docs/architecture.md`

---

## Current State

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. All 5 tabs working: Retro Games, PC Games, Watch, Listen, Settings. **1,547 tests passing.**

**What's new since Checkpoint 18:**

Backend optimizations (#17–#22):
- `/hubs/home/continueWatching` replaces `/library/onDeck` in `PlexClient.get_on_deck()`
- `PlexError` enum — typed error handling + exponential backoff retry in `_get()`
- Play queue (`POST /playQueues`) created before MPV launch; `playQueueItemID` in timeline reports
- `X-Plex-Client-Profile-Extra` header — codec capabilities sent to Plex for better direct-play decisions
- Playback history (`GET /status/sessions/history/all`) — more reliable recently-watched source
- Self-healing server connection — `PlexClient.set_fallback_urls()` / `try_next_connection()`, survives LAN IP changes

Backend features (#23–#24):
- `PlexEventListener` daemon thread — SSE `/:/eventsource/notifications`, triggers `refresh()` on `library.update/new/refresh.all`
- `PlexClient.rate()` + `PlexLibrary.rate()` slot — `PUT /:/rate` for star ratings (backend only, no UI yet)

UI features (#25–#27):
- Per-row focus memory in WatchScreen — `_focusMemory` dict replaces single `_resumeSavedIndex`
- In-app Plex PIN login — `PlexLoginOverlay.qml` + `startPlexPinLogin()` / `cancelPlexPinLogin()` slots; `plexLoginStatus` signal; no browser launch needed
- Loading overlay fixes — `_clearLoading()` helper with 400ms minimum display; overlay now shows correctly for Continue Watching, resume dialog, and slow network streams

Bug fixes:
- Plex PIN code was 24 chars (removed `strong=true` from `create_pin()`) — now correct 4-char link code
- Live TV channels with no guide data are now hidden (lineup-only channels excluded)
- MPV gamepad input enabled (`--input-gamepad=yes`)
- MPV input.conf v14 — correct button mapping for 8BitDo Micro D-input verified with `mpv --input-test`:
  - A (east, evdev 304) = `GAMEPAD_ACTION_DOWN` → pause/play
  - Start (evdev 315) = `GAMEPAD_START` → quit
  - D-pad seek/volume, L1/R1 audio/track, X/Y progress/subtitles
  - L2/R2 unbound (analog axis fires continuously — unusable without libmpv)

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
| 28 | libmpv migration (python-mpv) | Replace `MpvLauncher` subprocess + `MpvIpc` socket polling with `libmpv` via `python-mpv`. Enables: push-based `time-pos` observer (replaces 10s poll), `keybind()` API (eliminates `input.conf` versioning), L2/R2 seek (axis events controllable in-process), embedded video in Qt window. See scope below. |
| 29 | Rating UI — thumbs up/down on detail screen | Needs a free button; deferred until after libmpv migration frees up input.conf |
| 30 | Custom user-defined collections | Needs scoping |
| 31 | GOG/Epic Games Store | Needs spike first |
| 32 | Standalone emulator support (Dolphin, PCSX2) | Additive launcher extension |
| 33 | Gamepad extension: YouTube/Netflix | Browser extension work |
| 34 | Plex token encryption / OS keyring | Security hardening |
| 35 | Moonlight rich metadata | Deferred |

---

## Roadmap Item #28 — libmpv Migration Scope

**Why:** The current `MpvLauncher` subprocess + `MpvIpc` Unix socket approach has three hard limitations:
1. `PlexTimelineReporter` polls position every 10s via IPC — push-based `time-pos` observer would be instant and eliminate the polling thread entirely.
2. `input.conf` versioning is fragile — every button mapping change requires a version bump and file rewrite. `python-mpv`'s `keybind()` API sets bindings programmatically at runtime.
3. L2/R2 triggers are analog axes that fire continuously while held — uncontrollable from `input.conf`. In-process, the axis value can be read and debounced properly.

**What changes:**
- `MpvLauncher` → replaced by a `python-mpv` `MPV` instance embedded in the Qt window (`wid=str(int(window.winId()))`)
- `MpvIpc` → replaced by `player.time_pos`, `player.pause`, `player.audio`, `player.sub` properties
- `PlexTimelineReporter` → `@player.property_observer('time-pos')` callback instead of polling thread
- `input.conf` + `_ensure_input_conf()` → `player.keybind(name, command)` calls at startup
- `MpvSkipIntroOverlay` seek → `player.seek(ms / 1000)` instead of IPC JSON command
- Loading overlay: `player.wait_until_playing()` gives exact ready signal (no `processStarted` approximation)

**What stays the same:**
- All QML, all signals (`mpvStarted`, `mpvFinished`, `streamInfoReady`), all `PlexLibrary` slots
- Live TV launch (same approach, different MPV instance or same instance reused)
- Wayland/Xorg hwdec detection logic

**Estimated scope:** 3 tasks — (1) core MPV instance + property observers, (2) keybind migration + L2/R2 fix, (3) skip intro + subtitle track selection migration.

**Prerequisite:** `pip install mpv` (python-mpv). Requires `libmpv.so` on the system — already present since MPV is installed.

---

## Stack

| | |
|---|---|
| Framework | Qt 6 / QML + PySide6 (Python 3.10+) |
| Target | Linux x86_64, Xorg or Wayland, Intel J5005-class or better |
| Video playback | System MPV (`/usr/bin/mpv`), VA-API hwdec, direct Plex stream URLs (transient token) |
| Live TV | HDHomeRun direct streams + SiliconDust guide API (`api.hdhomerun.com`) |
| Emulator | RetroArch via Flatpak |
| PC games | Steam URI (`steam://rungameid/`), Moonlight CLI (Flatpak) |
| Plex music | Qt MediaPlayer + AudioOutput (direct Plex audio streams) |
| Browser | Brave Flatpak (music playback, MPV fallback) |
| Gamepad | evdev → synthetic QKeyEvent injection |
| Config | `~/.config/htpcstation/config.json` |
| MPV config | `~/.config/htpcstation/mpv/input.conf` (versioned v14, auto-written) |
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

**MPV on Wayland needs `--hwdec=vaapi-copy` and `--gpu-context=wayland`.** On Xorg use `--hwdec=vaapi` and `--gpu-context=x11`. `MpvLauncher._gpu_context()` and `_hwdec_mode()` auto-detect from `XDG_SESSION_TYPE`.

**Fedora ships codec-restricted packages.** `ffmpeg-free` → swap for `ffmpeg` (RPM Fusion). `libva-intel-media-driver` → swap for `libva-intel-driver` (RPM Fusion). `check-deps.sh` detects and reports these.

**`flatpak kill <app_id>` required to close Brave.** `QProcess.kill()` only kills the wrapper, not the sandboxed browser.

**Moonlight QSettings INI fields are all lowercase.** `hostname`, `localaddress`, `uuid` — not camelCase.

**Theme.qml: use semantic tokens, never `_palette` vars.** `_bg`, `_accent`, etc. are internal. QML files reference `colorBackground`, `colorAccent`, etc. `colorPrimary` and `colorSecondary` are kept as aliases for the 255 existing usages — rename them in 4b/4c.

**`PlexOnDeckGrid` and `PlexOnDeckList` expose `currentIndex` as a writable property** (not readonly). Writing to it from WatchScreen sets `_suppressIndexReset = true` first to prevent the `onActiveFocusChanged` handler from resetting to 0.

**`PlexTimelineReporter` uses a daemon thread.** It is started in `_on_mpv_started_for_timeline` and stopped in `_on_mpv_finished_for_timeline`. `PlexLibrary.shutdown()` also calls `stop()`. The reporter reads MPV position via `MpvIpc` every 10s.

**`_mpvLaunchReady` signal carries 8 args** `(url, title, start_ms, duration_ms, part_id, intro_start_ms, intro_end_ms, credits_start_ms)`. All test mocks must pass all 8.

**HDHomeRun guide API uses `DeviceAuth` token** from `http://{host}/discover.json`, not the Plex token. The guide endpoint is `https://api.hdhomerun.com/api/guide?DeviceAuth={token}`. The Plex cloud EPG grid endpoint (`/{epg_key}/grid`) ignores `channelGridKey` filter — do not use it for per-channel data.

**Plex EPG timestamps are unreliable** (may be ~1 year ahead of wall clock). Use HDHomeRun guide timestamps instead — they are accurate Unix seconds.

**MPV gamepad key names are SDL positional, not label-based.** On the 8BitDo Micro in D-input mode (Bluetooth), verified with `mpv --input-test`: A (east, evdev 304) = `GAMEPAD_ACTION_DOWN`, B (south, evdev 305) = `GAMEPAD_ACTION_RIGHT`, Start = `GAMEPAD_START`. L2/R2 are analog axes (`GAMEPAD_LEFT/RIGHT_TRIGGER`) that fire continuously while held — do not bind seek commands to them without in-process debouncing (requires libmpv migration, roadmap #28).

**`SDL_GAMECONTROLLERCONFIG` override has no effect on this device.** The 8BitDo Micro's SDL mapping is already correct in the system database. Do not attempt to override it.

**MPV `input.conf` version check only rewrites on version mismatch.** If you need to force a rewrite during development, delete `~/.config/htpcstation/mpv/input.conf` before launching.

---

## Dev Machine

- ThinkPad T480, i5-8350U (Kaby Lake-R), Intel UHD 620, Fedora 43, Wayland
- ROMs: `~/opencode/ROMs/` (gb, ngpc, sega32x)
- Steam: Flatpak, 5 games
- Moonlight: Flatpak, 1 paired host, 7 apps
- Plex: local server + HDHomeRun FLEX 4K tuner at `192.168.0.80`
- Controller: 8BitDo Micro in D-input mode (Bluetooth; D-pad as ABS_HAT0X/Y hat axes; face buttons BTN_SOUTH/EAST/NORTH/WEST; triggers BTN_TL2/TR2 + ABS_BRAKE/GAS axes)
- HDHomeRun DeviceAuth: in `discover.json` at `http://192.168.0.80/discover.json`
