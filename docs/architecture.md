# HTPC Station — Architecture Reference

> Full codebase structure, gotchas, and architecture notes.
> Session-start context: `resume-project.md` | Roadmap: `milestones.md` | History: `changelog.md`

---

## Codebase Structure

```
htpcstation/
  main.py                              # Entry point, PySide6 engine, context properties, font loading,
                                       # keyboard/gamepad detection, window hide/show on process launch
  assets/
    fonts/
      NotoEmoji-Regular.ttf            # Bundled emoji font (OFL) — loaded but Qt doesn't reliably use
                                       # it as fallback for all glyphs (see gotchas)
  backend/
    browser_launcher.py                # Brave kiosk launcher, dedicated user-data-dir, extension deploy
    config.py                          # JSON config, ~130 system defaults (all Knulli/Batocera folders),
                                       # all setters auto-save
    controller_mapping.py              # Controller mapping config: load/save, dual-record format,
                                       # build_evdev_lookup(), build_web_gamepad_mapping(),
                                       # generate_mapping_js()
    gamepad.py                         # evdev → QKeyEvent injection, auto-repeat, hotplug, raw mode,
                                       # startRawMode/stopRawMode (opens/closes SdlResolver),
                                       # getDeviceCapabilities(), setMpvActive()
    sdl_resolver.py                    # SdlResolver: ctypes SDL wrapper, probes libSDL2/libSDL3 at
                                       # import, opens SDL joystick on startRawMode, resolves evdev
                                       # events to SDL records via GameControllerDB (compiled into SDL).
                                       # seed_from_controller_mapping() builds primary lookup from saved
                                       # mapping. Module-level singleton: resolver.
    gamelist.py                        # gamelist.xml parser, write_game_stats()
    keys.py                            # Semantic key abstraction, input source tracking, button layout
    launcher.py                        # QProcess emulator launcher, async signal-based start
    library.py                         # GameLibrary QObject: models, collections, sort, launch, favorites
    live_tv_library.py                 # LiveTvLibrary QObject: HDHomeRun guide API fetch, guide cache,
                                       # warm/cold start, background refresh, LiveTvChannelModel
    live_tv_models.py                  # LiveTvChannel dataclass
    metadata_gamelist.py               # GameMetadata dataclass, gamelist.xml reader/writer (Steam + Moonlight)
    models.py                          # Game and System dataclasses
    moonlight_artwork.py               # Artwork cache: Steam Store lookup, CDN download, manual overrides
    moonlight_client.py                # Moonlight CLI wrapper: list_apps(), MoonlightLauncher (QProcess)
    moonlight_config.py                # Shared Moonlight directory helper (~/.config/htpcstation/moonlight/)
    moonlight_library.py               # MoonlightLibrary QObject: two-phase refresh, models, launch
    moonlight_models.py                # MoonlightHost, MoonlightApp dataclasses
    moonlight_parser.py                # Moonlight QSettings config parser, host discovery, TCP probe
    moonlight_play_history.py          # Play timestamp recording/reading (play_history.json)
    mpv_launcher.py                    # LibMpvPlayer: python-mpv in-process player, VA-API hwdec,
                                       # Wayland/Xorg auto-detect, programmatic keybinds, property
                                       # observers (time-pos, pause), live TV variant with reconnect options
    network_monitor.py                 # NetworkMonitor QObject: periodic connectivity check, online property
    plex_account.py                    # plex.tv API: OAuth, server discovery, home users, user switching
    plex_client.py                     # Plex Media Server HTTP client, get_stream_url(), report_timeline(),
                                       # persist_stream_selection(), mark_played/unplayed, transient token,
                                       # get_metadata(include_markers=True), get_markers()
    plex_library.py                    # PlexLibrary QObject: threaded data loading, models, sort/filter,
                                       # music slots, server/user management, MPV/browser launch,
                                       # My List (plex_mylist.json), subtitle IPC slots,
                                       # timeline reporter wiring, track persistence, skip intro markers,
                                       # fetchStreamInfo async, streamInfoReady signal
    plex_models.py                     # PlexMovie, PlexShow, PlexSeason, PlexEpisode, PlexArtist,
                                       # PlexAlbum, PlexTrack dataclasses
    poster_cache.py                    # Thread-safe poster downloader, SHA256 hash filenames
    retroarch_config.py                # read_cfg/write_cfg, HOTKEY_CFG_KEYS (triple keys per action:
                                       # _btn/_axis/_hat), build_hotkey_cfg() writes correct key type
                                       # from SDL record type (button/axis/hat)
    settings_manager.py                # SettingsManager QObject: wraps Config for QML, OAuth,
                                        # plexPlayer toggle (mpv/browser), RetroArch hotkey slots,
                                        # controller mapping slots, SDL record label resolution
    steam_config.py                    # Shared Steam directory helper (~/.config/htpcstation/steam/)
    steam_library.py                   # SteamLibrary QObject: models, sort, launch, recently played,
                                       # metadata fetch, favorites. GOG-ready source list model.
    steam_metadata.py                  # Steam Store API metadata fetcher (appdetails endpoint)
    steam_models.py                    # SteamGame dataclass
    steam_parser.py                    # ACF/VDF parser, game discovery, artwork resolution + caching
  extension/                           # Chromium browser extension (Manifest V3)
    manifest.json
    content.js                         # Gamepad API polling, edge detection, auto-repeat, Start+Select
    generated_mapping.js               # Auto-generated button mapping (written at deploy time)
    mappings/
      default.js                       # No-op fallback for non-Plex sites
      index.js                         # Site matcher
      plex.js                          # Plex Web mapping: player controls, virtual focus cursor,
                                       # popup/dropdown navigation, focus stack, stale focus recovery,
                                       # auto-user-select, auto-play, auto-expand mini player (~900 lines)
  qml/
    main.qml                           # ApplicationWindow, vpx(), QuitDialog
    Theme.qml                          # Singleton: two-layer token system — _palette vars (dark palette,
                                       # only these change between themes) + semantic tokens (colorAccent,
                                       # colorSurface, colorOverlay, colorBadgeSteam, etc.). colorPrimary
                                       # and colorSecondary kept as aliases. No hardcoded hex in any other
                                       # QML file.
    qmldir                             # Singleton registration
    components/
      ClockDisplay.qml
      FocusRing.qml
      NetworkIndicator.qml
      QuitDialog.qml
      SettingButton.qml
      SettingSelect.qml
      SettingSlider.qml
      SettingTextInput.qml
      SettingToggle.qml
    screens/
      HomeScreen.qml                   # Two-level launcher: Level 1 = background image + centered image
                                        # buttons (theme-driven); Level 2 = tab content loaded on demand.
                                        # Tab content destroyed on back() to prevent eager network calls.
                                        # MediaPlayer + AudioOutput, global X play/pause, MPV running state,
                                        # subtitle overlay trigger
      RetroGamesScreen.qml             # System list + game grid + detail (3-state)
      GameGridView.qml
      GameDetailView.qml
      GameListView.qml                 # Split-panel list view for retro games
      PcGamesScreen.qml                # Steam source list + game grid + detail (3-state), Steam Favorites
      MoonlightScreen.qml              # Moonlight source list (Recently Played, Favorites, Apps) + app grid + detail
      SteamGameGrid.qml
      SteamGameDetail.qml
      SteamGameList.qml
      MoonlightAppGrid.qml
      MoonlightAppDetail.qml
      MoonlightAppList.qml
      RecentlyPlayedGrid.qml           # Shared recently played / favorites grid (used by PC Games + Moonlight tabs)
      RecentlyPlayedList.qml
      RecentlyPlayedDetail.qml
      WatchScreen.qml                  # Plex library list + movie/show grids + detail + My List + Live TV
                                       # _playContent(): MPV or browser per settings.plexPlayer
                                       # resume dialog (viewOffset > 0)
      PlexMovieGrid.qml
      PlexMovieDetail.qml
      PlexMovieList.qml
      PlexShowGrid.qml
      PlexShowDetail.qml
      PlexShowList.qml
      PlexOnDeckGrid.qml               # Continue Watching / My List grid (configurable model + sourceTitle)
      PlexOnDeckList.qml
      LiveTvScreen.qml                 # Embedded Live TV channel guide
      MpvSubtitleOverlay.qml           # Always-on-top Window for subtitle track selection during MPV
      MpvSkipIntroOverlay.qml          # Always-on-top Window for skip intro button (bottom-right)
      ListenScreen.qml                 # Plex Music: menu, artists, albums, tracks, now playing
      ControllerMappingDialog.qml       # Full-screen wizard: 14 inputs, raw mode, co-firing collection,
                                        # hold-to-skip (skippable actions), Start+Select cancel,
                                        # auto-save on completion
      ModifierCaptureDialog.qml        # Modal overlay: capture one button/axis for hotkey modifier or
                                        # hotkey action; tap to assign, hold 3s to clear; 10s timeout
      RetroarchHotkeysScreen.qml       # Modifier row + 12 interactive hotkey rows + rewind settings +
                                        # Apply button; warns if mapping wizard not yet run
      SystemCoresScreen.qml            # Per-system RetroArch core editor
      SettingsScreen.qml               # 7-section settings menu, Video Player toggle (MPV/Browser)
  tests/
    conftest.py
    test_collections.py                # 22 tests
    test_controller_mapping.py         # 38 tests
    test_auto_mapping.py               # 31 tests
    test_sdl_resolver.py               # 688 tests (SdlResolver, seed_from_controller_mapping, resolve)
    test_retroarch_hotkeys.py          # ~120 tests (RetroarchHotkeysScreen backend slots)
    test_retroarch_config.py           # ~60 tests (read_cfg/write_cfg/build_hotkey_cfg)
    test_emulator_launch.py            # 24 tests
    test_filter_sort.py                # 12 tests
    test_gamelist_parser_fixes.py      # 7 tests
    test_live_tv_library.py            # ~38 tests (HDHomeRun guide API)
    test_moonlight_artwork.py          # 36 tests
    test_moonlight_client.py           # 24 tests
    test_moonlight_library.py          # 119 tests
    test_moonlight_parser.py           # 30 tests
    test_moonlight_play_history.py     # 20 tests
    test_mpv_launcher.py               # 45 tests
    test_network_monitor.py            # 13 tests
    test_pc_games_favorites.py         # 58 tests
    test_plex_account.py               # 45 tests
    test_plex_backend.py               # 191 tests
    test_plex_mylist.py                # 36 tests
    test_plex_stream.py                # 15 tests
    test_plex_client.py                # 11 tests (identity headers, timeline, track persistence)
    test_plex_timeline.py              # 10 tests (PlexTimelineReporter lifecycle + push interface)
    test_settings_backend.py           # 99 tests
    test_steam.py                      # 95 tests
    test_video_snap.py                 # 5 tests
    test_browser_launch.py             # 31 tests
    test_keys.py                       # 17 tests (key code changes: 1/2 replace F1/F2)
    test_gamepad_disconnect.py         # 10 tests (disconnect crash fix, hint flash fix)
```

---

## Architecture Notes

### Theme System
- Themes live in `themes/<name>/` relative to the app root.
- Active theme set via `Config.theme_name` (default: `"default"`), persisted in `config.json` under `"ui"`.
- `SettingsManager.themeName` (str) and `themeDir` (str, `file://` URL ending in `/`) expose the theme to QML.
- `APP_DIR = Path(__file__).parent` defined in `main.py`; passed to `SettingsManager` as `app_dir`.
- Theme assets for the homescreen: `home-background.png` (full-screen background), `<slug>-button.png` per tab (slugs: `retrogames`, `pcgames`, `moonlight`, `plexmedia`, `plexmusic`, `settings`).
- Fallback: if a button image fails to load (`Image.status !== Image.Ready`), a plain rectangle + text label is shown.
- Color palette swap (future 4b/4c work) is separate from the image theme system.
- Two-layer token structure (Theme.qml): `_palette` vars (internal, only these change between color themes) → semantic tokens (what QML files use). Never reference `_palette` vars directly from QML files.

### UI Layout Hierarchy

Every screen follows a three-level layout:

| Level | Height | Contents |
|---|---|---|
| `headerBar` | `vpx(56)` | `◀  Screen Title` (left-aligned). Title only — no hints. |
| `statusBar` | `vpx(28)` | Left: sort/status label. Right: button hints (`anchors.right`, `rightMargin: vpx(16)`). |
| Content area | fills remainder | Grid, list, detail, etc. Top margin `vpx(16)` from `statusBar.bottom`. |

Global status indicators (clock, network, now playing + ▶/■ symbol) live in `HomeScreen.qml`, anchored top-right, z-ordered above all content. The `rightMargin: vpx(16)` on hint Rows keeps hints flush under the indicators.

Button hint conventions:
- Accept (A/Enter) and Cancel (B/Escape) are **never** shown — universally understood.
- Keyboard shortcuts: Context1 = `1`, Context2 = `2`, PageUp/Down = `PgUp`/`PgDn`.
- Gamepad labels use `keys.context1Label`, `keys.context2Label`, etc. — always via the ternary `keys.useGamepadLabels ? ... : ...`.
- Hint text switches reactively via `keys.useGamepadLabels` (set by `Keys.setGamepadInput()` / `Keys.setKeyboardInput()`).

### QML Focus Management
- Every screen/component is a `FocusScope` with `enabled: focus`
- Gamepad events injected as `QKeyEvent`s — QML only sees keyboard events
- `FocusRing.qml` shows on `parent.activeFocus`
- `vpx()` lives on `ApplicationWindow` (id: `root`) — never shadow this id in components

### Threading Model
- All UI on Qt main thread
- Plex API calls via `ThreadPoolExecutor(max_workers=2)` (`self._executor`), results via Qt signals
- Poster downloads via dedicated `ThreadPoolExecutor(max_workers=10)` (`self._poster_executor`) — separate from main executor to avoid blocking library loads
- Moonlight host probing + app enumeration via `ThreadPoolExecutor(max_workers=2)`
- Emulator/browser/Moonlight launch via `QProcess` (async, non-blocking)
- Steam game discovery is synchronous (small local ACF file reads)
- Live TV: HDHomeRun `discover.json` sequential (fast, local), then `lineup.json` + guide API parallel (2 workers)
- `PlexTimelineReporter`: dedicated daemon `threading.Thread` (not executor) — fires every 10s, reads MPV position via IPC
- All internal signals that cross thread boundaries use `Qt.ConnectionType.QueuedConnection`

### Process Lifecycle
- **Emulators/Browser/Moonlight:** `processStarted` → `window.hide()`, `processFinished` → `window.showFullScreen()` + `raise_()` + `requestActivate()`
- **Steam:** No window management — game takes focus, WM handles return on exit
- **MPV:** Same hide/show pattern. `MpvLauncher.processStarted` → `plex.mpvStarted` → `homeScreen._mpvRunning = true`
- **Browser kill:** `GamepadManager.startSelectCombo` → `browser_launcher.kill()` → `flatpak kill <app_id>`

### Plex Architecture
- **`PlexAccount`** — talks to `plex.tv` for OAuth, server discovery, home users, user switching. Old `/api/` endpoints use XML + token as query param. OAuth methods are `@staticmethod`.
- **`PlexClient`** — talks to local media server. Always uses admin token. Sends full identity headers (`X-Plex-Client-Identifier`, `X-Plex-Product`, etc.) on every request. `get_stream_url(ratingKey)` returns `(url, view_offset_ms)`. `report_timeline()` is fire-and-forget (timeout=5s, never raises). `persist_stream_selection()` PUTs audio/subtitle choice with `allParts=1`. `get_transient_token()` returns short-lived delegation token for stream URLs.
- **`PlexLibrary`** — orchestrates both. Stores `_active_token` (user-specific) for browser deep links separately from admin token. Caches user token/title/content-rating-filter. On-deck skipped for managed users (server rejects their tokens). Owns `PlexTimelineReporter` — started/stopped via `processStarted`/`processFinished`. Stores `_current_play_part_id`, `_audio_id_map`, `_sub_id_map` for track persistence. `_mpvLaunchReady` signal carries 6 args: `(url, title, start_ms, duration_ms, part_id, intro_end_ms)`. Public signals: `markersReady(intro_end_ms: int)`, `mpvPositionChanged(int ms)`. Slot: `seekMpv(ms: int)`.
- **Poster cache:** `_poster_executor` (10 workers) separate from `_executor` (2 workers). Cached posters pre-resolved on worker thread before emitting to QML — no placeholder flash on warm load.

### MPV Architecture
- `LibMpvPlayer` (`backend/mpv_launcher.py`): in-process MPV via `python-mpv` (libmpv ctypes). Created with `wid=int(window.winId())` so MPV renders into the Qt window — no subprocess, no window hide/show. Auto-detects Wayland vs Xorg via `XDG_SESSION_TYPE`. Wayland → `hwdec=vaapi-copy, gpu_context=wayland`. Xorg → `hwdec=vaapi, gpu_context=x11`. Gamepad bindings registered via `player.keybind()` at startup — no `input.conf` file written to disk. Verified button names on 8BitDo Micro D-input: `GAMEPAD_ACTION_DOWN` (A/east = pause/play), `GAMEPAD_DPAD_*` (seek/volume), `GAMEPAD_LEFT/RIGHT_SHOULDER` (audio/tracks), `GAMEPAD_ACTION_LEFT` (Y = subtitle picker), `GAMEPAD_ACTION_UP` (X = show-progress), `GAMEPAD_START` (quit). L2/R2 use `on_key_press` callbacks with 0.5s debounce — one seek per tap.
- `processStarted` signal fires from `wait_until_playing()` (first frame ready), not from process start. `processFinished` fires from `end_file` event callback. Both are marshalled to the main thread via `QMetaObject.invokeMethod`.
- `MpvSubtitleOverlay.qml`: in-process `FocusScope` overlay (not a separate `Window`) — works correctly since MPV renders in the same Qt window. Triggered by Y button via `subtitlePickerRequested` signal chain (`LibMpvPlayer` → `PlexLibrary` → QML). Calls `plex.getMpvSubtitleTracks()` / `plex.setMpvSubtitleTrack()` / `plex.persistTrackSelection()`.
- `PlexTimelineReporter` (`backend/plex_timeline.py`): daemon thread, POSTs to `/:/timeline` every 10s. Position updated via push-based `@property_observer('time-pos')` callback (registered in `PlexLibrary.set_wid()`). Pause state updated via `@property_observer('pause')`. No polling. Sends `"stopped"` on exit. Session identified by per-play `uuid4()`.
- Stream URLs use transient token (`GET /security/token?type=delegation&scope=all`) — long-lived token never exposed to the player.
- `MpvIpc` (Unix socket IPC client) removed. All position/state reads use libmpv property observers.

### Live TV Architecture
- `LiveTvLibrary`: fetches HDHomeRun host from Plex `/livetv/dvrs`, then uses HDHomeRun's own APIs for all guide data. No Plex cloud EPG calls.
- **Data sources:**
  - `GET http://{host}/discover.json` → `DeviceAuth` token (local, instant)
  - `GET http://{host}/lineup.json` → 67 tunable channels with VCN, name, stream URL (local, instant)
  - `GET https://api.hdhomerun.com/api/guide?DeviceAuth={token}` → 58 channels with full guide (cloud, ~2s)
- **Current program detection:** `StartTime <= now < EndTime` — HDHomeRun timestamps are accurate Unix seconds.
- **Cache:** `~/.config/htpcstation/livetv_cache/guide_cache.json` — single file, all channels. Warm start serves cache instantly, background refresh updates in-place.
- **Force refresh:** Y button in guide clears cache and re-fetches.
- **Why not Plex cloud EPG:** The `/{epg_key}/grid` endpoint ignores `channelGridKey` filter — returns the same 607-item cross-channel dataset regardless. Only 19 of 64 channels appeared, only 5 with live data. HDHomeRun guide gives 58 channels, 56 with live data.

### Steam Architecture
- `steam_parser.py`: VDF/ACF recursive descent parser. Discovers games from Flatpak + native paths. Filters non-games (Proton, runtimes, incomplete installs).
- `steam_library.py`: `SteamSourceListModel` (extensible — designed for future GOG/Epic sources) + `SteamGameListModel`. `toggleFavorite(index)` persists to `gamelist.xml`. `getFavorites()` returns `{source: "steam", ...}` — source key required for badge rendering. Steam-only: no Moonlight injection.
- Artwork: custom override → HTPC cache → local Steam cache → CDN download. Always returns local path.

### Moonlight Architecture
- Two-phase refresh: Phase 1 (sync, local config read) → Phase 2 (threaded: TCP probe + app enumeration + artwork + play history).
- `artwork_index.json` tracks `steam_app_id` per app — used for future rich metadata.
- `MoonlightLibrary` owns its own `getRecentlyPlayed()` (reads `moonlight_play_history.py`, returns up to 20 entries sorted by `last_played` desc) and `clearRecentlyPlayed()`. No injection into `SteamLibrary`.
- `MoonlightScreen.qml`: dedicated tab with sources (Recently Played, Favorites, Apps), app grid/list, detail view. View mode persisted via `settings.moonlightViewMode` — `on_ViewModeChanged` overrides child components' `setPcGamesViewMode()` calls.

### Browser Extension Architecture
- No ES modules — files concatenated via manifest `js` array: `generated_mapping.js` → `mappings/*.js` → `content.js`
- `generated_mapping.js` written at deploy time from `controller_mapping.json` via `generate_mapping_js()`, which reads the **SDL half** of each dual-record entry and translates to Web Gamepad API button/axis indices. Falls back to a comment-only stub if no SDL data recorded yet.
- Deployed to `~/.var/app/com.brave.Browser/config/htpcstation-extension/` before each launch
- Flatpak override `--filesystem=/run/udev:ro` applied automatically for gamepad access

### Gamepad / Controller Mapping Architecture

**Dual-record format** (since M8-B, CP32). Every entry in `controller_mapping.json` has:
```json
{
  "evdev": {"type": "button"|"axis", "code": <int>, "value": <int>},
  "sdl":   {"type": "button"|"axis"|"hat", ...} | null,
  "also":  [{"evdev": {...}, "sdl": {...}}]
}
```
- `evdev` half — used by `gamepad.py` (`build_evdev_lookup()`) for Qt key injection and by `LibMpvPlayer` (same path).
- `sdl` half — used by `build_hotkey_cfg()` for `retroarch.cfg` and by `build_web_gamepad_mapping()` for the browser extension.
- `also` array — co-firing events from dual-reporting devices (D-input triggers emit both an axis event and a button event for the same physical press). Both are stored; `seed_from_controller_mapping()` registers all of them in the SDL lookup.
- Old single-record format (pre-M8-B) is migrated transparently by `load_mapping()`: wraps existing record as `evdev` half, sets `sdl` to `null`.

**SDL resolution lifecycle:**
1. `GamepadManager.startRawMode()` → calls `SdlResolver.open(device_name, button_codes, axis_codes)`, then `seed_from_controller_mapping(load_mapping())`.
2. Raw mode active → `rawInput` signal emits `(evtype, code, value)` to QML dialogs.
3. QML captures input → calls `settings.saveControllerMapping(recordedList)` or `settings.setHotkeyModifier/setHotkeyActionByEvdev/ByAxis()` — all call `resolver.resolve()` while resolver is still open.
4. `GamepadManager.stopRawMode()` → calls `SdlResolver.close()`.
5. **Critical ordering:** emit `buttonCaptured`/`axisCaptured` signals (which trigger `settings` slots) **before** calling `stopRawMode()`. `ModifierCaptureDialog` and `ControllerMappingDialog` both follow this order.

**SdlResolver.resolve() priority:**
1. `_evdev_event_to_sdl` — seeded from saved controller mapping via `seed_from_controller_mapping()`. Covers all inputs the user physically pressed during the mapping wizard with correct labels.
2. `_evdev_axis_to_sdl_record` — built from `SDL_GameControllerGetBindForAxis()` heuristic during `open()`. Fallback for inputs not in the mapping (e.g. Home/Guide button).
3. `_evdev_button_to_sdl` — sorted-position fallback for buttons (EV_KEY codes → SDL button indices by sort order).

**D-input trigger detection** (critical gotcha): D-input devices report triggers as SDL joystick **buttons** (not axes). `SdlResolver.open()` detects this: GC API axis binds that map to joystick buttons are identified by finding which joystick axis indices are **not** bound to any GC logical axis. Those unbound joystick axis indices correspond to evdev axis codes that SDL treats as buttons. The resolver stores a `{"type": "button", ...}` record for those evdev axis codes so `build_hotkey_cfg()` writes `input_*_btn` (not `input_*_axis`) for RetroArch.

**Hotkey modifier** is always written as `input_enable_hotkey_btn` — axis/hat modifiers are not supported by RetroArch. `build_hotkey_cfg()` writes `nul` for axis/hat keys of the modifier regardless of the SDL record type.

**Duplicate prevention:** `_store_hotkey_sdl()` evicts any other hotkey action or the modifier that already uses the same SDL record before assigning the new one. Prevents RetroArch receiving the same button for two functions.

**Face button label layout mapping:**
- SDL always uses Xbox button names internally: A=East, B=South, X=West, Y=North.
- Standard layout (Nintendo-style): A=East, B=South, **X=North, Y=West** — SDL X and Y are swapped vs display labels.
- Alternate layout (Xbox-style): A=South, B=East, X=West, Y=North — SDL names match display labels except A↔B swap.
- `_FACE_LABELS_STANDARD` / `_FACE_LABELS_ALTERNATE` maps in `settings_manager.py` translate SDL label → display label + cardinal position (e.g. "A (East)").

**Hold-to-skip in mapping wizard** (`ControllerMappingDialog.qml`): skippable actions (triggers, shoulders) show a 3s hold timer. Button tap → records on release. Button hold 3s → skips. Known issue: dual-reporting inputs (D-input triggers) fire an axis event first (starts timer, sets `_holdSkipCode`), then a button event hits the `else` branch and calls `_recordInput` immediately. Fix needed: ignore button press events when `_holdSkipCode !== -1`.

### Config File Structure

```json
{
  "rom_directory": "/path/to/ROMs",
  "retroarch": {
    "command": "flatpak run org.libretro.RetroArch",
    "cores_directory": "~/.var/app/org.libretro.RetroArch/config/retroarch/cores"
  },
  "systems": { "gb": { "display_name": "Game Boy", "core": "gambatte_libretro.so", "extensions": [".gb"] } },
  "plex": { "token": "...", "server_id": "...", "user_id": 0, "player": "mpv", "client_id": "<stable-uuid>" },
  "browser": { "command": "flatpak run com.brave.Browser" },
  "moonlight": { "command": "flatpak run com.moonlight_stream.Moonlight", "host_uuid": "..." },
  "ui": { "video_snap_autoplay": true, "video_snap_delay_ms": 1500, "show_network_indicator": true, "button_layout": "standard", "moonlight_view_mode": "grid", "theme_name": "default" },
  "tabs": { "show_retro_games": true, "show_pc_games": true, "show_moonlight": true, "show_watch": true, "show_listen": true },
  "hotkey_modifier_evdev": 316,
  "hotkey_modifier_sdl": {"type": "button", "sdl_button": 5, "label": "Guide"},
  "hotkey_mapping": {
    "save_state": {"type": "button", "sdl_button": 2, "label": "X"},
    "exit_emulator": {"type": "hat", "sdl_hat": 0, "dir": "down"}
  },
  "rewind_enable": false,
  "rewind_buffer_size": 100,
  "rewind_granularity": 8
}
```

---

## Full Gotchas Catalogue

### QML
- **`id: root` shadowing** — Never use in components. `vpx()` is on the ApplicationWindow's `root`.
- **Signal name conflicts** — Never name a signal `<propertyName>Changed`. QML auto-generates those.
- **Property bindings don't re-evaluate for API calls** — Use `optionsProvider` function called on demand, not static bindings.
- **QString to int** — Use `parseInt(value)` in QML before passing to `@Slot(int)`.
- **Image source local paths** — Need `"file://"` prefix. Check `startsWith("http")` before prepending.
- **Context property null on startup** — Guard all bindings: `plex ? plex.model : null`.
- **HomeScreen tab arrays** — Build imperatively in `Component.onCompleted`, never via bindings to `settings.*`. Binding causes cascading focus destruction and app freeze.
- **One `Component.onCompleted` per scope** — QML silently fails with "Property value set multiple times" if you have two.
- **PySide6 custom signals in `Connections`** — May not work. Use reactive property bindings or imperative code instead.
- **Missing `}` in SettingsScreen handler chain** — Silently breaks the entire Settings tab with no console error.
- **Stderr filter hides QML errors** — Disable `_start_stderr_filter()` in `main.py` when debugging QML.
- **`HomeScreen` tab content is loaded on demand** — `Loader.source` starts as `""`. Set it imperatively on A-press; clear it in `returnFocusToTabBar()` to destroy the screen and stop network calls. Do not bind `Loader.source` to any property.

### Plex
- **Managed user tokens get 401 from server** — Always use admin token for server API calls. User token only for browser deep links.
- **No on-deck for managed users** — Server rejects managed user tokens on on-deck endpoint. Hide Continue Watching for managed users.
- **Content rating filter must be cached** — Store alongside user token; restore on `_setup_client()`.
- **User token caching** — Only call `switch_user()` when user ID changes. Cache `_cached_user_token/title/content_rating_filter`.
- **`selectServer`/`selectUser` must not block** — Save config and invalidate client only. Lazy reconnect on next `refresh()`.
- **Old plex.tv API endpoints** — `/api/home/users` requires token as query param, returns XML.
- **Plex Web user selection** — Cannot be bypassed via URL. Extension auto-clicks matching user tile.
- **Deep link lost after user selection** — Extension saves URL, waits 1.5s, re-navigates.
- **Auto-play requires `hashchange` listener** — Content script runs once; re-navigation is a hash change.
- **`--autoplay-policy=no-user-gesture-required`** — Required for `video.play()` from content scripts.
- **Plex class name hashes change between versions** — Always use `[class*="prefix"]`, never exact class names.
- **Escape must be dispatched on overlay element** — Not on `document`.
- **Bare `.click()` doesn't work on React buttons** — Need full pointer event sequence: `pointerdown` → `mousedown` → `pointerup` → `mouseup` → `click`.
- **React re-renders swap DOM elements** — Save focus coordinates before click; use `elementFromPoint()` to find replacement.
- **Focus stack pollution** — Only push on layer-opening clicks (`aria-haspopup` or known trigger `data-testid`).
- **Virtual scrollers break index-based navigation** — Use position-based navigation (Y coordinate comparison).
- **Mini player `<video>` triggers `isPlayerActive()`** — Check for `AudioVideoFullPlayer` (full-screen only).

### Brave / Browser
- **Flatpak `--user-data-dir` outside sandbox ignored** — Use path inside sandbox: `~/.var/app/com.brave.Browser/config/htpcstation-browser/`.
- **Existing Brave instance ignores flags** — Dedicated `--user-data-dir` creates separate process.
- **Session accumulation** — Clear `Sessions/` and `Session Storage/` before each launch.
- **`window.close()` blocked in kiosk mode** — Use `flatpak kill <app_id>`.
- **Flatpak browsers can't see gamepads** — Apply `flatpak override --user <app_id> --filesystem=/run/udev:ro`.

### Steam
- **Don't hide window on Steam launch** — `xdg-open` exits immediately; can't track game exit. WM handles focus return automatically.
- **`getFavorites()` must include `source: "steam"`** — Badge renderer treats anything not `"steam"` as Moonlight.

### Moonlight
- **QSettings INI fields are all lowercase** — `hostname`, `localaddress`, `uuid`, not camelCase.
- **`customname=false` means no custom name** — Not the string "false".
- **CLI spawns Qt GUI** — Stderr has SDL/Qt noise; ignore entirely.
- **Steam search accuracy** — Non-game apps may match wrong results. Users can drop custom artwork in `artwork_custom/`.

### MPV
- **Wayland needs `vaapi-copy`** — `vaapi` direct display path doesn't work without a copy step on Wayland EGL.
- **Fedora codec-restricted packages** — `ffmpeg-free` causes `libopenh264` to win H.264 decoder selection over VA-API. Swap for `ffmpeg` from RPM Fusion. `libva-intel-media-driver` → `libva-intel-driver` (RPM Fusion).
- **AV1 requires Gen 12+ hardware** — Kaby Lake (UHD 620) has no AV1 hardware decode.
- **`mpv-libs` required** — `python-mpv` loads `libmpv.so` at runtime. On Fedora: `sudo dnf install mpv-libs`. On Debian/Ubuntu: `sudo apt-get install libmpv2`. The `mpv` binary alone is not sufficient.
- **`LibMpvPlayer.set_wid()` must be called after `window.showFullScreen()`** — `winId()` is only valid after the window is mapped. Call `plex_library.set_wid(int(window.winId()))` in `main.py` after `showFullScreen()`.
- **Gamepad button names are SDL positional, not label-based** — The 8BitDo Micro uses `hint:!SDL_GAMECONTROLLER_USE_BUTTON_LABELS` in its SDL mapping. Verified with `mpv --input-test`: A (east, evdev 304) = `GAMEPAD_ACTION_DOWN`, B (south, evdev 305) = `GAMEPAD_ACTION_RIGHT`. Always verify with `mpv --input-gamepad=yes --input-test --force-window --idle --input-conf=/dev/null` on the actual device.
- **`SDL_GAMECONTROLLERCONFIG` override is ignored** — The 8BitDo Micro's mapping is already in the system SDL database and cannot be overridden via env var on this device.
- **L2/R2 debounce uses `on_key_press` callback with 0.5s window** — The analog axis fires continuously while held. The debounce closure uses a `[float]` list to capture mutable state across calls. Do not use `{no-repeat}` in keybinds — it has no effect on axis-held state.
- **`_mpvLaunchReady` carries 6 args** — `(url, title, start_ms, duration_ms, part_id, intro_end_ms)`. All test mocks must match this signature.
- **`processStarted` fires from `wait_until_playing()`, not from process start** — The signal is emitted when the first frame is ready. `processFinished` fires from the `end_file` event callback. Both are marshalled to the main thread via `QMetaObject.invokeMethod`.
- **python-mpv callbacks run on the mpv event thread** — Never call Qt UI methods directly from a property observer or event callback. Always use `QMetaObject.invokeMethod` with `QueuedConnection`.

### Plex API
- **Plex cloud EPG `channelGridKey` filter is broken** — The `/{epg_key}/grid` endpoint ignores `channelGridKey` and returns the same full dataset regardless. Use HDHomeRun guide API instead.
- **Plex EPG timestamps may be ~1 year ahead** — The cloud EPG provider returns `beginsAt`/`endsAt` in seconds but offset by ~1 year from wall clock. Do not use for current-program detection. Use HDHomeRun timestamps.
- **`hubs/discover` endpoint takes 26 seconds** — The `/{epg_key}/hubs/discover` endpoint times out with the 10s `_TIMEOUT`. Do not use.
- **Timeline reports use `timeout=5`** — Not `_TIMEOUT=10`. Timeline is fire-and-forget; never raise.
- **Markers are at top level of metadata item** — `metadata.get("Marker", [])`, not inside `Media.Part.Stream`. Type field is `"intro"` or `"credits"`.
- **Transient token replaces long-lived token in stream URL** — `get_transient_token()` returns `""` on failure; fall back to main token silently.

### Gamepad
- **evdev crash loop** — `OSError` catch must wrap the entire `for event in events:` loop, not just `.read()`.
- **Gamepad disconnect segfault** — `_cleanup()` must disconnect the `QSocketNotifier` signal (`activated.disconnect`) and call `deleteLater()` on both the notifier and the handler before removing from the dict. Python GC drops the handler reference before Qt's C++ object tree is cleaned up — if the notifier has a pending activation queued, it fires into a deleted object. `_remove_device()` must call `handler.deleteLater()`, not just `pop()`.
- **Hint label flash on gamepad connect** — `QSocketNotifier` fires immediately on creation if the device fd has buffered kernel events. Use a `_ready` flag (set to `True` after the first `_on_readable` call) to suppress `setGamepadInput()` until the user has actually pressed a button.
- **Auto-repeat timers leak into raw mode** — `startRawMode()` must call `_release_all_keys()`.
- **Mapping dialog can't use Accept/Cancel** — Auto-save on completion; no confirmation button.
- **D-input D-pad as ABS_X/ABS_Y** — Normalize 0-255 range to -1/0/1 using axis range.
- **D-input triggers are SDL buttons, not SDL axes** — `SdlResolver.open()` detects this via the GameController API: any GC logical axis whose bind type is `BINDTYPE_BUTTON` is a trigger mapped as a joystick button. The resolver stores a button SDL record for those evdev axis codes. `build_hotkey_cfg()` must write `_btn`, not `_axis`. If you see `nul` for a trigger hotkey in retroarch.cfg, the trigger was not detected as a button during resolver open.
- **SDL library probing order matters** — `libSDL2-2.0.so.0` is probed first. On Fedora 43 this is `sdl2-compat` (SDL2 shim over SDL3) — function signatures are identical to real SDL2. Do not probe SDL3 before SDL2 or you may get a different GameControllerDB version than RetroArch uses.
- **`seed_from_controller_mapping()` must be called after `open()`** — It builds the primary lookup from the saved mapping (source of truth for all inputs the user actually pressed). The GC API heuristics in `open()` are fallback only. If called before `open()`, `_evdev_hat_to_sdl` is empty and hat axis entries in the mapping will not be skipped correctly.
- **`resolve()` returns `None` when joystick is not open** — Always call `open()` before calling `resolve()`. The `ModifierCaptureDialog` and `ControllerMappingDialog` both emit signals before calling `stopRawMode()` specifically to ensure the resolver is still open when `settings` slots call `resolve()`.
- **Emit capture signals before `stopRawMode()`** — `stopRawMode()` calls `SdlResolver.close()`, which clears all lookup tables. Any `settings.setHotkeyActionByEvdev/ByAxis()` call that needs to resolve an SDL record must happen before `stopRawMode()`.
- **Hold-to-skip dual-reporting bug** — In `ControllerMappingDialog`, dual-reporting inputs (D-input triggers) fire an axis event followed by a button event for the same physical press. The axis event starts the hold timer (`_holdSkipCode = axisCode`). The button event (different code) then hits the `else` branch and calls `_recordInput` immediately. Fix: ignore button press events when `_holdSkipCode !== -1`.
- **`rawInput` emits value=0 for releases** — Raw mode was extended in M6-V2 to emit both press (`value=1`) and release (`value=0`) events for buttons so `ModifierCaptureDialog` can detect tap-vs-hold. The `_handle_button` guard is `if value in (0, 1)` — auto-repeat (`value=2`) is explicitly excluded.

### Other
- **Bundled emoji font** — Qt doesn't reliably use NotoEmoji as fallback. Use text equivalents (❤️→♥, 🎵→♫).
- **Unicode Dingbats block causes font fallback stutter** — Characters in the Dingbats block (U+2700–U+27BF, e.g. U+275A `❚`) are not present in the `"Sans"` system font. Qt scans all installed fonts for a fallback glyph at startup and on every render until cached — causes slow load and layout stutter. Use Geometric Shapes (U+25A0–U+25FF: `■`, `▶`, `▲`) or Block Elements (U+2580–U+259F) which are in every standard Linux system font.
- **VAAPI decoding errors in video snaps** — Set `LIBVA_MESSAGING_LEVEL=0` in `main.py`.
- **Qt 6 Video type** — Use explicit `MediaPlayer` + `VideoOutput` with 100ms+ delay before `play()`.
- **`git filter-repo` can be too aggressive** — Review replacement patterns before running.

---

## Temporary Decisions

| Decision | Location | Future Fix |
|---|---|---|
| Plex token in plaintext config.json | `config.json` | Encrypt or use OS keyring |
| Synchronous `getMovie()`/`getShow()` | `plex_library.py` | Move to threaded worker |
| Synchronous `testPlexConnection()` | `settings_manager.py` | Defer to thread |
| Auto-user-select 1.5s fixed delay | `extension/mappings/plex.js` | Detect navigation completion |
| Moonlight artwork: Steam search only | `moonlight_artwork.py` | Add IGDB/RAWG fallback |
| Moonlight detail view lacks metadata | `MoonlightAppDetail.qml` | Wire up gamelist.xml + Steam API via cached steam_app_id |

---

## Gamepad Controls

Default mapping (standard layout, A=East):

| Physical Button | evdev Code | Qt Key | Action |
|---|---|---|---|
| Face East (Accept) | BTN_EAST (305) | Key_Return | Accept / launch |
| Face South (Cancel) | BTN_SOUTH (304) | Key_Escape | Cancel / back |
| Face North | BTN_NORTH (307) | Key_1 | Context 1 (favorite/My List) |
| Face West | BTN_WEST (308) | Key_2 | Context 2 (sort/subtitle) |
| Start | BTN_START (315) | Key_F10 | Quit dialog |
| Select | BTN_SELECT (314) | Key_F9 | Secondary menu |
| Left Shoulder | BTN_TL (310) | Key_PageUp | Quick scroll |
| Right Shoulder | BTN_TR (311) | Key_PageDown | Quick scroll |
| Left Trigger | ABS_Z (2) | Key_Home | Page scroll up |
| Right Trigger | ABS_RZ (5) | Key_End | Page scroll down |
| D-pad | ABS_HAT0X/Y | Key_Up/Down/Left/Right | Navigate |
| Start + Select | — | — | Close browser |

Button Layout setting swaps both display labels AND functional mapping.

---

## History

Checkpoint history and task brief archive: `docs/changelog.md`
