# HTPC Station — Architecture Reference

> Full codebase structure, gotchas, architecture notes, and checkpoint history.
> For the lean session-start context, see `resume-project.md`.

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
    controller_mapping.py              # Controller mapping config: load/save, default mapping, evdev lookup
    gamepad.py                         # evdev → QKeyEvent injection, auto-repeat, hotplug, raw mode
    gamelist.py                        # gamelist.xml parser, write_game_stats()
    keys.py                            # Semantic key abstraction, input source tracking, button layout
    launcher.py                        # QProcess emulator launcher, async signal-based start
    library.py                         # GameLibrary QObject: models, collections, sort, launch, favorites
    live_tv_library.py                 # LiveTvLibrary QObject: EPG fetch (Plex cloud), HDHomeRun stream
                                       # URLs, parallel per-channel schedule fetch, LiveTvChannelModel
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
    mpv_ipc.py                         # MpvIpc: Unix socket client for MPV JSON IPC (track list, subtitle
                                       # and audio track selection)
    mpv_launcher.py                    # MpvLauncher: QProcess MPV subprocess, VA-API hwdec, Wayland/Xorg
                                       # auto-detect, versioned input.conf, IPC socket, resume via --start,
                                       # live TV variant with reconnect options
    network_monitor.py                 # NetworkMonitor QObject: periodic connectivity check, online property
    plex_account.py                    # plex.tv API: OAuth, server discovery, home users, user switching
    plex_client.py                     # Plex Media Server HTTP client, get_stream_url() for direct play
    plex_library.py                    # PlexLibrary QObject: threaded data loading, models, sort/filter,
                                       # music slots, server/user management, MPV/browser launch,
                                       # My List (plex_mylist.json), subtitle IPC slots
    plex_models.py                     # PlexMovie, PlexShow, PlexSeason, PlexEpisode, PlexArtist,
                                       # PlexAlbum, PlexTrack dataclasses
    poster_cache.py                    # Thread-safe poster downloader, SHA256 hash filenames
    settings_manager.py                # SettingsManager QObject: wraps Config for QML, OAuth,
                                       # plexPlayer toggle (mpv/browser)
    steam_config.py                    # Shared Steam directory helper (~/.config/htpcstation/steam/)
    steam_library.py                   # SteamLibrary QObject: models, sort, launch, recently played,
                                       # metadata fetch, favorites, PC Favorites source
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
    Theme.qml                          # Singleton: colors, fonts, animation durations
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
      HomeScreen.qml                   # Tab bar, content loader, MediaPlayer + AudioOutput,
                                       # global X play/pause, MPV running state, subtitle overlay trigger
      RetroGamesScreen.qml             # System list + game grid + detail (3-state)
      GameGridView.qml
      GameDetailView.qml
      GameListView.qml                 # Split-panel list view for retro games
      PcGamesScreen.qml                # Source list + game grid + detail (3-state), PC Favorites
      SteamGameGrid.qml
      SteamGameDetail.qml
      SteamGameList.qml
      MoonlightAppGrid.qml
      MoonlightAppDetail.qml
      MoonlightAppList.qml
      RecentlyPlayedGrid.qml           # Unified Steam+Moonlight recently played / PC Favorites grid
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
      ListenScreen.qml                 # All music views: menu, artists, albums, tracks, now playing
      ControllerMappingDialog.qml
      SystemCoresScreen.qml            # Per-system RetroArch core editor
      SettingsScreen.qml               # 7-section settings menu, Video Player toggle (MPV/Browser)
  tests/
    conftest.py
    test_collections.py                # 22 tests
    test_controller_mapping.py         # 38 tests
    test_auto_mapping.py               # 31 tests
    test_emulator_launch.py            # 24 tests
    test_filter_sort.py                # 12 tests
    test_gamelist_parser_fixes.py      # 7 tests
    test_live_tv_library.py            # 38 tests
    test_moonlight_artwork.py          # 36 tests
    test_moonlight_client.py           # 24 tests
    test_moonlight_library.py          # 119 tests
    test_moonlight_parser.py           # 30 tests
    test_moonlight_play_history.py     # 20 tests
    test_mpv_ipc.py                    # 12 tests
    test_mpv_launcher.py               # 45 tests
    test_network_monitor.py            # 13 tests
    test_pc_games_favorites.py         # 58 tests
    test_plex_account.py               # 45 tests
    test_plex_backend.py               # 191 tests
    test_plex_mylist.py                # 36 tests
    test_plex_stream.py                # 15 tests
    test_settings_backend.py           # 99 tests
    test_steam.py                      # 95 tests
    test_video_snap.py                 # 5 tests
    test_browser_launch.py             # 31 tests
```

---

## Architecture Notes

### QML Focus Management
- Every screen/component is a `FocusScope` with `enabled: focus`
- Gamepad events injected as `QKeyEvent`s — QML only sees keyboard events
- `FocusRing.qml` shows on `parent.activeFocus`
- `vpx()` lives on `ApplicationWindow` (id: `root`) — never shadow this id in components

### Threading Model
- All UI on Qt main thread
- Plex API calls via `ThreadPoolExecutor(max_workers=2)`, results via Qt signals
- Moonlight host probing + app enumeration via `ThreadPoolExecutor(max_workers=2)`
- Poster downloads on thread pool, `dataChanged` emitted on main thread
- Emulator/browser/Moonlight launch via `QProcess` (async, non-blocking)
- Steam game discovery is synchronous (small local ACF file reads)
- Live TV EPG: discovery phase sequential (paginated), per-channel fetch parallel (8 workers)

### Process Lifecycle
- **Emulators/Browser/Moonlight:** `processStarted` → `window.hide()`, `processFinished` → `window.showFullScreen()` + `raise_()` + `requestActivate()`
- **Steam:** No window management — game takes focus, WM handles return on exit
- **MPV:** Same hide/show pattern. `MpvLauncher.processStarted` → `plex.mpvStarted` → `homeScreen._mpvRunning = true`
- **Browser kill:** `GamepadManager.startSelectCombo` → `browser_launcher.kill()` → `flatpak kill <app_id>`

### Plex Architecture
- **`PlexAccount`** — talks to `plex.tv` for OAuth, server discovery, home users, user switching. Old `/api/` endpoints use XML + token as query param. OAuth methods are `@staticmethod`.
- **`PlexClient`** — talks to local media server. Always uses admin token. `get_stream_url(ratingKey)` returns `(url, view_offset_ms)` for direct MPV play.
- **`PlexLibrary`** — orchestrates both. Stores `_active_token` (user-specific) for browser deep links separately from admin token. Caches user token/title/content-rating-filter. On-deck skipped for managed users (server rejects their tokens).

### MPV Architecture
- `MpvLauncher`: subprocess MPV, auto-detects Wayland vs Xorg via `XDG_SESSION_TYPE`. Wayland → `--hwdec=vaapi-copy --gpu-context=wayland`. Xorg → `--hwdec=vaapi --gpu-context=x11`. Versioned `input.conf` (v2) auto-written to `~/.config/htpcstation/mpv/input.conf`, overwritten when outdated.
- `MpvIpc`: Unix socket client for `--input-ipc-server=/tmp/htpcstation-mpv.sock`. Used for subtitle track list query and selection.
- `MpvSubtitleOverlay.qml`: always-on-top `Window`, shown when Y pressed during MPV playback (Watch tab only). Calls `plex.getMpvSubtitleTracks()` / `plex.setMpvSubtitleTrack()`.

### Live TV Architecture
- `LiveTvLibrary`: fetches EPG provider key from `/media/providers`, HDHomeRun host from `/livetv/dvrs`. Paginates `/{epg_provider}/grid` to discover all channel gridKeys, then fetches each channel's schedule in parallel (8 workers, 5 programs per channel). Stream URL: `http://{hdhomerun_host}:5004/auto/v{vcn}`.
- EPG endpoint: `{server_url}/tv.plex.providers.epg.cloud:N/grid?type=1&gridStartTime={now-43200}&gridEndTime={now+7200}`
- Current program: `beginsAt <= now < endsAt` OR `onAir=True` in Media object. Next: first program with `beginsAt >= now` that isn't current.

### Steam Architecture
- `steam_parser.py`: VDF/ACF recursive descent parser. Discovers games from Flatpak + native paths. Filters non-games (Proton, runtimes, incomplete installs).
- `steam_library.py`: `SteamSourceListModel` (sources including PC Favorites when non-empty) + `SteamGameListModel`. `toggleFavorite(index)` persists to `gamelist.xml`. `getFavorites()` returns `{source: "steam", ...}` — source key required for badge rendering.
- Artwork: custom override → HTPC cache → local Steam cache → CDN download. Always returns local path.

### Moonlight Architecture
- Two-phase refresh: Phase 1 (sync, local config read) → Phase 2 (threaded: TCP probe + app enumeration + artwork + play history).
- `artwork_index.json` tracks `steam_app_id` per app — used for future rich metadata.
- Moonlight hosts injected into Steam's `SteamSourceListModel` via `setMoonlightSources()`.

### Browser Extension Architecture
- No ES modules — files concatenated via manifest `js` array: `generated_mapping.js` → `mappings/*.js` → `content.js`
- `generated_mapping.js` written at deploy time from `controller_mapping.json`, translating evdev codes to Web Gamepad API indices
- Deployed to `~/.var/app/com.brave.Browser/config/htpcstation-extension/` before each launch
- Flatpak override `--filesystem=/run/udev:ro` applied automatically for gamepad access

### Config File Structure

```json
{
  "rom_directory": "/path/to/ROMs",
  "retroarch": {
    "command": "flatpak run org.libretro.RetroArch",
    "cores_directory": "~/.var/app/org.libretro.RetroArch/config/retroarch/cores"
  },
  "systems": { "gb": { "display_name": "Game Boy", "core": "gambatte_libretro.so", "extensions": [".gb"] } },
  "plex": { "token": "...", "server_id": "...", "user_id": 0, "player": "mpv" },
  "browser": { "command": "flatpak run com.brave.Browser" },
  "moonlight": { "command": "flatpak run com.moonlight_stream.Moonlight", "host_uuid": "..." },
  "ui": { "video_snap_autoplay": true, "video_snap_delay_ms": 1500, "show_network_indicator": true, "button_layout": "standard" }
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

### Gamepad
- **evdev crash loop** — `OSError` catch must wrap the entire `for event in events:` loop, not just `.read()`.
- **Auto-repeat timers leak into raw mode** — `startRawMode()` must call `_release_all_keys()`.
- **Mapping dialog can't use Accept/Cancel** — Auto-save on completion; no confirmation button.
- **D-input D-pad as ABS_X/ABS_Y** — Normalize 0-255 range to -1/0/1 using axis range.

### Other
- **Bundled emoji font** — Qt doesn't reliably use NotoEmoji as fallback. Use text equivalents (❤️→♥, 🎵→♫).
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
| Face North | BTN_NORTH (307) | Key_F1 | Context 1 (favorite/My List) |
| Face West | BTN_WEST (308) | Key_F2 | Context 2 (sort/subtitle) |
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

## Checkpoint History

- **CP 1** — M0+M1: shell, retro games
- **CP 2** — Settings UI
- **CP 3** — Plex server discovery, browser extension, M6 hardening
- **CP 4** — Plex polish
- **CP 5** — M3 Steam
- **CP 6** — M4 Moonlight
- **CP 7** — M5 Home Screen
- **CP 8** — Controller mapping, Flatpak gamepad access, Plex modal navigation, button layout
- **CP 9** — Plex player popup/dropdown navigation, layered cancel, focus stack, stale focus recovery
- **CP 10** — Auto-expand minimized player, auto-resume playback, autoplay policy flag
- **CP 11** — M5 rich metadata for Steam, grid spacing fix, UI navigation improvements
- **CP 12** — Listen tab backend
- **CP 13** — Full Listen tab v1
- **CP 14** — Now Playing view, persistent background playback, global play/pause, sort persistence, tab visibility, Clear Recently Played
- **CP 15** — Public release prep (README, MIT license, PII sanitization, requirements.txt, check-deps), list views for all tabs, LT/RT quick jump, Plex Live TV gamepad navigation
- **CP 16** — PC Games Favorites, System Cores settings, SYSTEM_DEFAULTS expansion (~130 systems), Plex My List, MPV video player (VA-API, Wayland, resume, subtitle overlay), embedded Live TV guide (EPG + HDHomeRun), hardware-aware check-deps

---

## Task Brief Archive

All task briefs at `~/opencode/misc/coding-team/`:
- `m0-shell/` (001–004), `m1-games/` (005–014), `m2-plex/` (015–020)
- `deferred-batch-1/` (021–024), `settings/` (025–026)
- `m6-hardening-pullforward/` (001–003), `browser-gamepad-extension/` (001–004)
- `plex-server-discovery/` (001–004), `plex-polish/` (001–003)
- `m3-steam/` (001–003), `m4-moonlight/` (001–012)
- `plex-show-pagination/` (001), `plex-live-tv/` (001)
- `m5-home-screen/` (001–006), `plex-resume-modal/` (001)
- `controller-mapping/` (001–003), `plex-player-popups/` (001–005)
- `plex-mini-player-expand/` (001–004), `dpad-up-to-tabbar/` (001)
- `m5-rich-metadata/` (001–004, Steam complete, Moonlight pending)
- `listen-tab/` (001–012), `remember-sort/` (001), `phase1-bugs/` (001)
- `kernel-headers-dep/` (001–002), `pc-games-favorites/` (001–003)
- `system-cores-settings/` (001), `system-defaults-expansion/` (001)
- `plex-watchlist/` (001–002), `plex-mylist/` (001–002)
- `mpv-player/` (001–004), `mpv-subtitle-overlay/` (001)
