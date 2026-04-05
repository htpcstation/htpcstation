# HTPC Station — Resume Document (Checkpoint 24)

> Hand this file to a fresh agent to resume development.
> For full codebase structure, gotchas, architecture notes, and history: `docs/architecture.md`

---

## Current State

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. All 5 tabs working: Retro Games, PC Games, Watch, Listen, Settings. **1,590 tests passing.**

**What's new since Checkpoint 21:**

Hardening Batch 1 + 2 + partial Batch 3 (see `docs/harden.md` for full backlog):

### Batch 1 — crash and stuck-UI fixes
- **C1**: `_mpvLaunchReady.emit()` fixed from 8 args to 5 (matched `Signal(str,str,int,int,int)`)
- **C3**: `assert` in `config.set_plex_player` replaced with guard + warning (safe under `-O`)
- **C4**: `_save_my_list` wrapped in `try/except OSError`
- **M1**: `wait_until_playing` timeout now emits `_emit_finished` so loading overlay clears
- **M3**: `InvalidMedia` handled separately from `EndOfMedia` — bad URL no longer auto-advances
- **H6**: `_artists_cache_path` uses `CONFIG_DIR / "poster_cache"` (was hardcoded `~/.config/htpcstation`)
- **M9**: `config.save()` wrapped in `try/except OSError`

### Batch 2 — UX fixes
- **H7**: `plex.plexError` wired to error banner in `WatchScreen` — auth/network errors now visible
- **H8**: B from show detail (entered via My List) now returns to My List (added `_showDetailOrigin`)
- **H4**: Three `target: plex` Connections blocks consolidated into one
- **B2-3**: `_routeFocus()` and `onActiveFocusChanged` guard against stealing focus from modal overlays (`_resumeDialogVisible`, `_loadingOverlayVisible`)

### Listen tab seek bar fixes
- `MediaPlayer.seek()` does not exist in Qt6 — replaced all calls with `musicPlayer.position =`
- Progress bar `FocusScope` → plain `Item` with `focus: true` (FocusScope never received key events)
- Mouse drag added to progress bar via `MouseArea` with `hoverEnabled` + `cursorShape`
- `homeScreen._seekTo(ms)` added for absolute seeking

### Watch tab loading/cancel hardening
- Loading overlay: 20s hard timeout (`loadingTimeoutTimer`), B to cancel, `[B] Cancel` hint
- Cancel during load: `_mpvLaunched` flag tracks whether `plex.playWithMpv()` was called; `_cancelledDuringLoad` flag stops MPV when `onMpvPlaybackReady` fires after cancel
- `plex.stopMpv()` slot added to `PlexLibrary` (calls `_mpv_launcher.kill()`)
- `kill()` now sets `_cancel_requested` event and dispatches `player.stop()` off-thread (non-blocking)
- `vid = "no"` set before `player.play()` — video suppressed during buffering; re-enabled in `_wait_and_signal` after cancel check, preventing flash on cancel
- `focusRestoreTimer` (50ms) calls `_routeFocus()` after loading overlay hides
- `loadingOverlay.onVisibleChanged` uses `forceActiveFocus()` instead of `focus:` binding
- `onMpvFinished` ignores stale finish events when `_mpvLaunched` is true (new launch in progress)
- Resume dialog: loading overlay stays as backdrop until dialog is dismissed; `loadingOverlayTimer` skips hide while `_resumeDialogVisible`; confirm path keeps overlay visible through `_launchMpv`

### My List navigation
- Show detail entered from My List: `_showDetailOrigin = "mylist"` set; B returns to My List with saved focus index

### Alt+F4 during MPV playback (GNOME/Wayland)
- On GNOME/Wayland, `fullscreen=yes` causes MPV to own a separate compositor surface; Alt+F4 destroys it at the compositor level (bypasses Qt event filter)
- Alt+F4 triggers libmpv's internal `quit` (not `stop`), destroying the core and raising `ShutdownError` on any subsequent property access
- `_on_shutdown` callback: stashes dead player in `_dead_player`, nulls `_player`, schedules `_recreate_player` via `QueuedConnection`
- `_recreate_player` (main thread): calls `dead_player.terminate()` → releases Wayland surface (zombie gone from Alt+~) → calls `set_wid(self._wid)` to create fresh core
- `_show_window_after_mpv`: calls `window.hide()` then `showFullScreen()` after 150ms — forces Qt to recreate the Wayland surface after Mutter destroys it
- `launch()` and `launch_live_tv()` force-stop and proceed if `is_running()` is true (zombie recovery fallback)
- Event filter on `window` intercepts `QEvent.Type.Close` and calls `plex.stopMpv()` when MPV is running

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
| 29 | Hardening Batch 1+2 | ✅ Done — see `docs/harden.md` |
| 30 | ~~Hardening Batch 3~~ | ✅ Done — H2 (async fetch*), H3 (loading timeout), C2 (pagination — low risk, deferred), H5/M8 (shared MPV _mpv_active flag) |

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

**Only ONE `Component.onCompleted` per QML scope.** QML silently fails with "Property value set multiple times".

**Plex managed user tokens get 401 from the media server.** Always use the admin token for server API calls.

**MPV on Wayland needs `hwdec=vaapi-copy` and `gpu_context=wayland`.** On Xorg use `hwdec=vaapi` and `gpu_context=x11`. Auto-detected from `XDG_SESSION_TYPE`.

**`fullscreen=yes` is required in `mpv.MPV()` kwargs.** Without it, OS UI elements (status bar) remain visible over the video. On GNOME/Wayland this causes MPV to own a separate compositor surface — Alt+F4 destroys it at the Mutter level. Recovery: `_show_window_after_mpv` calls `window.hide()` then `showFullScreen()` after 150ms.

**`MediaPlayer.seek()` does not exist in Qt6.** Use `musicPlayer.position = ms` for seeking.

**`FocusScope` does not receive `Keys` events unless a focusable child exists.** Use a plain `Item` with `focus: true` instead when you need key handling without child focus delegation.

**`_routeFocus()` and `onActiveFocusChanged` in WatchScreen guard against modal overlays.** Always check `_resumeDialogVisible` and `_loadingOverlayVisible` before redirecting focus.

**`_mpvLaunchReady` signal carries 5 args** `(url, title, start_ms, duration_ms, part_id)`. All test mocks must match this signature.

**`_mpvLaunched` flag in WatchScreen.** Set to `true` when `plex.playWithMpv()` is called, cleared in `onMpvPlaybackReady` (success) or `_clearLoading()` (cancel). `onMpvFinished` ignores stale finish events when `_mpvLaunched` is true.

**`vid = "no"` set before `player.play()`.** Video suppressed during buffering to prevent flash on cancel. Re-enabled in `_wait_and_signal` after `_cancel_requested` check.

**`kill()` is non-blocking.** Sets `_cancel_requested` event immediately, dispatches `player.stop()` off-thread. Safe to call from Qt main thread.

**Alt+F4 calls libmpv `quit`, not `stop`.** This destroys the core. `_on_shutdown` callback detects this, stashes the dead player, and schedules `_recreate_player` on the main thread. `_recreate_player` calls `terminate()` on the dead player (releases Wayland surface) then `set_wid()` to create a fresh core. Never call `terminate()` from the mpv event thread — use `QueuedConnection` to the main thread.

**`_wid` is stored on first `set_wid()` call** so `_recreate_player` can recreate without external input. `set_wid()` is idempotent after a shutdown — it checks `self._player is not None` before creating.

**`PlexTimelineReporter.stop()` calls `thread.join(timeout=5)`.** This blocks the calling thread for up to 5s. It is called from `_on_mpv_finished_for_timeline` which runs on the main thread via signal. Only fires after `processStarted` — not on cancel (where `processStarted` is suppressed).

**`LibMpvPlayer.set_wid()` must be called after `window.showFullScreen()`.** `winId()` is only valid after the window is mapped.

**`LibMpvPlayer.launch()` sets `pause=False` before `play()`.** MPV can retain a paused state across loads.

**Fedora ships codec-restricted packages.** `ffmpeg-free` → swap for `ffmpeg` (RPM Fusion). `check-deps.sh` detects and reports these.

**`flatpak kill <app_id>` required to close Brave.** `QProcess.kill()` only kills the wrapper.

**Moonlight QSettings INI fields are all lowercase.** `hostname`, `localaddress`, `uuid`.

**Theme.qml: use semantic tokens, never `_palette` vars.**

**`PlexOnDeckGrid` and `PlexOnDeckList` expose `currentIndex` as writable.** Writing sets `_suppressIndexReset = true` first.

**HDHomeRun guide API uses `DeviceAuth` token** from `http://{host}/discover.json`. The Plex cloud EPG grid endpoint ignores `channelGridKey` — do not use it for per-channel data.

**Plex EPG timestamps are unreliable.** Use HDHomeRun guide timestamps instead.

**MPV gamepad key names are SDL positional, not label-based.** Dpad scrobbling uses `GAMEPAD_DPAD_LEFT/RIGHT`. L2/R2 are not bound.

**python-mpv callbacks run on the mpv event thread.** Never call Qt UI methods directly — use `QMetaObject.invokeMethod` with `QueuedConnection`.

---

## Dev Machine

- ThinkPad T480, i5-8350U, Intel UHD 620, Fedora 43, Wayland (GNOME/Mutter)
- ROMs: `~/opencode/ROMs/` (gb, ngpc, sega32x)
- Steam: Flatpak, 5 games
- Moonlight: Flatpak, 1 paired host, 7 apps
- Plex: local server + HDHomeRun FLEX 4K tuner at `192.168.0.2`
- Controller: 8BitDo Micro in D-input mode (Bluetooth)
- HDHomeRun DeviceAuth: in `discover.json` at `http://192.168.0.2/discover.json`
