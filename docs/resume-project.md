# HTPC Station — Resume Document (Checkpoint 18)

> Hand this file to a fresh agent to resume development.
> For full codebase structure, gotchas, architecture notes, and history: `docs/architecture.md`

---

## Current State

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. All 5 tabs working: Retro Games, PC Games, Watch, Listen, Settings. **1,485 tests passing.**

**What's new since Checkpoint 17:**

MPV UX overhaul:
- Gamepad controls in MPV fixed (v3 input.conf: `GAMEPAD_ACTION_RIGHT/DOWN/DPAD_*`)
- Loading overlay with 400ms minimum display on Play press
- Async `fetchStreamInfo` + `playWithMpv` — no main-thread blocking
- Resume dialog cancel restores focus to previously selected item
- My List respects MPV/browser player setting; shows navigate to show detail
- Sort/filter slots guard against synthetic section keys (`_mylist`, `_ondeck`)

Plex playback reporting (P0):
- `X-Plex-Client-Identifier` stable UUID + full identity headers on every request
- `PlexTimelineReporter` — daemon thread, `POST /:/timeline` every 10s while MPV plays
- Track persistence: `PUT /library/parts/{partId}` syncs audio/subtitle choice to all Plex clients
- Transient token: MPV stream URLs use short-lived delegation token

Plex P1 features:
- Mark watched/unwatched (Y button on detail screens, optimistic update)
- Skip intro overlay (`MpvSkipIntroOverlay.qml`) — reads `Marker` array from metadata
- `plex.skipIntro()` seeks MPV via IPC to `intro_end_ms`

Poster cache improvements:
- Dedicated `_poster_executor` (10 workers) for poster downloads
- Pre-resolve cached posters before emitting to QML — eliminates placeholder flash on warm load
- Skip download tasks for already-cached items

Live TV overhaul:
- Replaced Plex cloud EPG (broken per-channel filter, 19 channels, 5 with live data) with HDHomeRun guide API
- `GET api.hdhomerun.com/api/guide?DeviceAuth=...` — 58 channels, 56 with currently-airing programs, ~2s load
- `GET http://{host}/lineup.json` — 67 tunable channels with stream URLs
- Accurate Unix timestamps — `StartTime <= now < EndTime` works correctly
- Channel logos from HDHomeRun `ImageURL`
- Single `guide_cache.json` replaces 19+ per-channel cache files
- Warm start: instant from cache, background refresh in parallel

---

## Roadmap

| # | Item | Notes |
|---|---|---|
| 1 | ~~F3 — PC Games Favorites~~ | ✅ Done |
| 2 | ~~C2 — System Cores settings~~ | ✅ Done |
| 3 | Moonlight rich metadata | Deferred — nearly free when resumed (steam_app_id already in artwork_index.json) |
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
| 16 | Plex token encryption / OS keyring | Security hardening |
| 17 | `/hubs/home/continueWatching` swap | ⚡ Backend only — one-line endpoint change in `PlexClient.get_on_deck()` |
| 18 | Typed error handling + retry (`PlexError` enum) | ⚡ Backend only — `_get()` currently returns `None` for all errors; add transient/permanent distinction + exponential backoff |
| 19 | Plex play queue (`POST /playQueues`) | ⚡ Backend only — enables Plex Companion; improves timeline accuracy with `playQueueItemID` |
| 20 | `X-Plex-Client-Profile-Extra` header | ⚡ Backend only — tells Plex our codec capabilities → better direct-play decisions |
| 21 | Playback history (`GET /status/sessions/history/all`) | ⚡ Backend only — more reliable recently-watched data source |
| 22 | Self-healing server connection | ⚡ Backend only — retry all known server addresses on failure; survives LAN IP changes |
| 23 | Server events SSE (`/:/eventsource/notifications`) | ⚡ Backend only — reactive library refresh when Plex scan completes |
| 24 | Rating (`PUT /:/rate`) | Minimal UI — thumbs up/down on detail screen; backend is one method |
| 25 | Focus memory per row (WatchScreen) | UI — generalise `_resumeSavedIndex` to `_focusMemory` dict |
| 26 | Hero/header fade on content focus | UI — `WatchScreen` header opacity animation |
| 27 | In-app Plex login | UI — needed for first-run wizard (roadmap #7) |
| 28 | Plex search | UI — new navigation flow |
| 29 | Custom user-defined collections | Needs scoping |
| 30 | GOG/Epic Games Store | Needs spike first |
| 31 | Standalone emulator support (Dolphin, PCSX2) | Additive launcher extension |
| 32 | Gamepad extension: YouTube/Netflix | Browser extension work |
| 33 | Plex token encryption / OS keyring | Security hardening (was #16) |
| 34 | Moonlight rich metadata | Deferred — nearly free when resumed (steam_app_id already in artwork_index.json) |

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
| MPV config | `~/.config/htpcstation/mpv/input.conf` (versioned v3, auto-written) |
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
| `plex` | PlexLibrary | Plex data, models, sort/filter, MPV/browser launch, My List, subtitle IPC, timeline reporting, track persistence, markers |
| `liveTV` | LiveTvLibrary | HDHomeRun guide + streams, MPV launch, guide cache |
| `gamepadManager` | GamepadManager | Raw mode for mapping dialog, device capabilities |
| `networkMonitor` | NetworkMonitor | Periodic connectivity check |
| `settings` | SettingsManager | Config read/write for settings UI, OAuth |

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

---

## Dev Machine

- ThinkPad T480, i5-8350U (Kaby Lake-R), Intel UHD 620, Fedora 43, Wayland
- ROMs: `~/opencode/ROMs/` (gb, ngpc, sega32x)
- Steam: Flatpak, 5 games
- Moonlight: Flatpak, 1 paired host, 7 apps
- Plex: local server + HDHomeRun FLEX 4K tuner at `192.168.0.80`
- Controller: 8BitDo Micro in D-input mode (D-pad as ABS_X/ABS_Y, no analog sticks)
- HDHomeRun DeviceAuth: in `discover.json` at `http://192.168.0.80/discover.json`
