# HTPC Station — Resume Document (Checkpoint 25)

> Hand this file to a fresh agent to resume development.
> For full codebase structure, gotchas, architecture notes, and history: `docs/architecture.md`

---

## Current State

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. All 5 tabs working: Retro Games, PC Games, Watch, Listen, Settings. **1,683 tests passing.**

Checkpoint 25 work is **complete but not yet committed** (working tree has uncommitted changes).

**What's new since Checkpoint 24:**

### Skip Intro (auto-seek)
- `auto_skip_intro` bool setting added to `Config`, `SettingsManager`, and Settings screen ("Auto-Skip Intro" toggle)
- `playWithMpv` worker calls `get_metadata(include_markers=True)`; parses `Marker` array for `type == "intro"` → `intro_end_ms`
- `_mpvLaunchReady` signal extended from 5 to **6 args**: `(url, title, start_ms, duration_ms, part_id, intro_end_ms)`
- `markersReady(intro_end_ms: int)` public signal emitted from `_on_mpv_launch_ready`
- `mpvPositionChanged(int)` public signal — push-based from `observe_time_pos`, marshalled via `_mpvPositionMs` internal signal + `QueuedConnection`
- `seekMpv(ms: int)` slot — calls `player.seek(ms / 1000.0, "absolute")`
- `WatchScreen`: `onMarkersReady` stores `_introEndMs`; `onMpvPositionChanged` auto-seeks + shows "Skipping intro..." toast; `_introSkipped` flag prevents re-triggering; markers cleared on each new launch

### Watch screen header fade
- `_contentFocused` bool on `WatchScreen`; `libraryListArea` fades to 30% opacity with 160ms `NumberAnimation` when content grid/list has focus; restores on library list or detail view; managed entirely through `_routeFocus()`

### Test coverage (Batch 3 follow-up — new untracked files)
- `tests/test_poster_cache.py` — locking, partial-file cleanup, thread-safety, download failure
- `tests/test_plex_timeline_reporter.py` — start/stop, heartbeat loop, position/pause updates
- `tests/test_config_edge_cases.py` — missing/empty/malformed file, partial config, save roundtrip, OSError, validation, `auto_skip_intro`
- `tests/test_skip_intro.py` — marker parsing, `_mpvLaunchReady` 6-arg emit, `markersReady`, `seekMpv`, config roundtrip

### Updated existing tests
- `tests/test_harden_batch1.py` — C1 test updated: `_mpvLaunchReady` now expects 6 args
- `tests/test_plex_stream.py` — all `_mpvLaunchReady` mock calls updated to 6 args

---

## Uncommitted changes (checkpoint 25)

```
modified:   backend/config.py
modified:   backend/plex_library.py
modified:   backend/settings_manager.py
modified:   docs/resume-project.md
modified:   qml/screens/SettingsScreen.qml
modified:   qml/screens/WatchScreen.qml
modified:   tests/test_harden_batch1.py
modified:   tests/test_plex_stream.py

untracked:  misc/coding-team/skip-intro-header-tests/
untracked:  tests/test_config_edge_cases.py
untracked:  tests/test_plex_timeline_reporter.py
untracked:  tests/test_poster_cache.py
untracked:  tests/test_skip_intro.py
```

---

## Roadmap

| # | Item | Notes |
|---|---|---|
| 1 | ~~F3 — PC Games Favorites~~ | ✅ Done |
| 2 | ~~C2 — System Cores settings~~ | ✅ Done |
| 3 | Moonlight rich metadata | Deferred |
| 4 | ~~F4 — Plex My List~~ | ✅ Done |
| 5 | ~~UI Refresh 4a — token interface + Theme.qml palettes~~ | ✅ Done |
| 6 | On-screen keyboard | Needed for gamepad-only wizard text input |
| 7 | X1 — First-run setup wizard | Built on new tokens + OSK |
| 8 | UI Refresh 4b/4c — QML token replacement + theme switcher | High blast radius |
| 9 | ~~Listen tab enhancements~~ | ✅ Done — shuffle/repeat/seek/lyrics |
| 10 | ~~Mark watched/unwatched (Plex)~~ | ✅ Done |
| 11 | Plex search | New navigation flow |
| 28 | ~~libmpv migration~~ | ✅ Done |
| 29 | ~~Hardening Batch 1+2+3~~ | ✅ Done — see `docs/harden.md` |
| 30 | ~~Skip Intro + header fade + test gaps~~ | ✅ Done (uncommitted) |

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
./htpcstation.sh          # after install.sh
python3 main.py           # direct

# Test
python3 -m pytest tests/ -q

# Check dependencies
bash scripts/check-deps.sh

# Install
bash install.sh
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

**QML context properties are null on first render.** Guard all bindings: `plex ? plex.model : null`.

**Never use `id: root` in any QML component.** That id belongs to the ApplicationWindow where `vpx()` is defined.

**Never name a signal `<propertyName>Changed`.** QML auto-generates those — conflict makes the component type "unavailable".

**HomeScreen tab arrays must be built imperatively, not via bindings.** Build in `Component.onCompleted` only.

**Only ONE `Component.onCompleted` per QML scope.**

**Plex managed user tokens get 401 from the media server.** Always use the admin token for server API calls.

**MPV on Wayland needs `hwdec=vaapi-copy` and `gpu_context=wayland`.** On Xorg use `hwdec=vaapi` and `gpu_context=x11`. Auto-detected from `XDG_SESSION_TYPE`.

**`fullscreen=yes` is required in `mpv.MPV()` kwargs.** Without it, OS UI elements remain visible. On GNOME/Wayland this causes MPV to own a separate compositor surface — Alt+F4 destroys it at the Mutter level. Recovery: `_show_window_after_mpv` calls `window.hide()` then `showFullScreen()` after 150ms.

**Alt+F4 calls libmpv `quit`, not `stop`.** Destroys the core. `_on_shutdown` callback stashes dead player, schedules `_recreate_player` on main thread. `_recreate_player` calls `terminate()` (releases Wayland surface) then `set_wid()` for fresh core. Never call `terminate()` from the mpv event thread.

**`MediaPlayer.seek()` does not exist in Qt6.** Use `musicPlayer.position = ms`.

**`FocusScope` does not receive `Keys` events unless a focusable child exists.** Use plain `Item` with `focus: true`.

**`_routeFocus()` and `onActiveFocusChanged` in WatchScreen guard against modal overlays.** Always check `_resumeDialogVisible` and `_loadingOverlayVisible` before redirecting focus.

**`_mpvLaunchReady` signal carries 6 args** `(url, title, start_ms, duration_ms, part_id, intro_end_ms)`. All test mocks must match this signature.

**`_mpvLaunched` flag in WatchScreen.** Set when `plex.playWithMpv()` is called, cleared in `onMpvPlaybackReady` (success) or `_clearLoading()` (cancel). `onMpvFinished` ignores stale events when `_mpvLaunched` is true.

**`vid = "no"` set before `player.play()`.** Video suppressed during buffering to prevent flash on cancel. Re-enabled in `_wait_and_signal` after cancel check.

**`kill()` is non-blocking.** Sets `_cancel_requested`, dispatches `player.stop()` off-thread.

**`PlexTimelineReporter.stop()` calls `thread.join(timeout=5)`.** Blocks calling thread up to 5s. Called from `_on_mpv_process_finished` on main thread — only fires after `processStarted`, not on cancel.

**`_mpv_active` flag in both `PlexLibrary` and `LiveTvLibrary`.** Gates all MPV signals — Plex and Live TV signals never cross-fire.

**`mpvPositionChanged(int)` fires continuously during playback.** Connected in `WatchScreen` for intro skip. Keep handlers lightweight — they run on every position tick.

**`seekMpv(ms)` uses `player.seek(ms / 1000.0, "absolute")`.** python-mpv seek takes seconds (float), not ms.

**`LibMpvPlayer.set_wid()` must be called after `window.showFullScreen()`.** `winId()` is only valid after the window is mapped.

**`LibMpvPlayer.launch()` sets `pause=False` before `play()`.** MPV can retain paused state across loads.

**Fedora ships codec-restricted packages.** `ffmpeg-free` → swap for `ffmpeg` (RPM Fusion). `check-deps.sh` detects and reports these.

**`flatpak kill <app_id>` required to close Brave.** `QProcess.kill()` only kills the wrapper.

**Moonlight QSettings INI fields are all lowercase.** `hostname`, `localaddress`, `uuid`.

**Theme.qml: use semantic tokens, never `_palette` vars.**

**`PlexOnDeckGrid` and `PlexOnDeckList` expose `currentIndex` as writable.** Writing sets `_suppressIndexReset = true` first.

**HDHomeRun guide API uses `DeviceAuth` token** from `http://{host}/discover.json`.

**Plex EPG timestamps are unreliable.** Use HDHomeRun guide timestamps instead.

**MPV gamepad key names are SDL positional, not label-based.** Dpad scrobbling uses `GAMEPAD_DPAD_LEFT/RIGHT`. L2/R2 not bound.

**python-mpv callbacks run on the mpv event thread.** Never call Qt UI methods directly — use `QMetaObject.invokeMethod` with `QueuedConnection`.

**Markers are at top level of metadata item.** `metadata.get("Marker", [])`, not inside `Media.Part.Stream`. Type field is `"intro"` or `"credits"`. Pass `include_markers=True` to `get_metadata()`.

---

## Dev Machine

- ThinkPad T480, i5-8350U, Intel UHD 620, Fedora 43, Wayland (GNOME/Mutter)
- ROMs: `~/opencode/ROMs/` (gb, ngpc, sega32x)
- Steam: Flatpak, 5 games
- Moonlight: Flatpak, 1 paired host, 7 apps
- Plex: local server + HDHomeRun FLEX 4K tuner at `192.168.0.2`
- Controller: 8BitDo Micro in D-input mode (Bluetooth)
- HDHomeRun DeviceAuth: in `discover.json` at `http://192.168.0.2/discover.json`
