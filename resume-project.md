# HTPC Station — Project Resume Document (Checkpoint 9)

> Hand this file to a fresh agent context to resume development without losing progress.
> Previous checkpoints: Checkpoint 1 (M0+M1), Checkpoint 2 (Settings UI), Checkpoint 3 (Plex server discovery, browser extension, M6 hardening), Checkpoint 4 (Plex polish), Checkpoint 5 (M3 Steam), Checkpoint 6 (M4 Moonlight), Checkpoint 7 (M5 Home Screen), Checkpoint 8 (controller mapping, Flatpak gamepad access, Plex modal navigation, button layout). This checkpoint covers Plex player popup/dropdown navigation, layered cancel, focus stack, stale focus recovery, and DOM architecture lessons.

---

## 1. Project Summary

**HTPC Station** turns any old mini PC or thin client into a living room entertainment hub. It is a single 10-foot gamepad-navigable interface that unifies retro game emulation, PC gaming via Steam, game streaming via Moonlight, and Plex media browsing — all from one home screen.

**Core principle:** HTPC Station owns browsing, metadata, and navigation. Launch backends handle execution — emulators, Steam URI, Moonlight CLI, Plex Web. HTPC Station is a launcher and library browser, not a media player or emulator.

**Original proposal:** `***REMOVED***opencode/proposal.md` (v3.0). Many decisions have been revised during implementation — this document is the authoritative current state.

---

## 2. Repository

- **Location:** `***REMOVED***opencode/htpcstation/`
- **Remote:** `git@github.com:htpcstation/htpcstation.git`
- **Branch:** `main`
- **Tests:** 842 passing (`python3 -m pytest tests/ -q`)
- **Run:** `cd ***REMOVED***opencode/htpcstation && python3 main.py`
- **Dependencies:** `pip install PySide6 evdev requests`
- **Dev machine:** ThinkPad T460, dual-core CPU, Fedora Linux (lower spec than target J5005)

**Reference data:**
- ROMs: `***REMOVED***opencode/ROMs/` (3 systems: gb, ngpc, sega32x with gamelist.xml, screenshots, videos)
- Steam: `***REMOVED***.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/` (Flatpak, 5 games)
- Moonlight: `***REMOVED***.var/app/com.moonlight_stream.Moonlight/config/Moonlight Game Streaming Project/Moonlight.conf` (Flatpak, 1 paired host, 7 apps)
- Moonlight data: `***REMOVED***.config/htpcstation/moonlight/` (artwork_scraped/, artwork_custom/, artwork_index.json, play_history.json)
- Steam artwork cache: `***REMOVED***.config/htpcstation/steam/` (artwork_scraped/, artwork_custom/)
- Controller mapping: `***REMOVED***.config/htpcstation/controller_mapping.json` (evdev codes + device capabilities)
- Plex API spec: `***REMOVED***opencode/openapi.json` (Plex Media Server OpenAPI 3.1)
- ES-DE reference: `***REMOVED***opencode/es-de/`
- Pegasus reference: `***REMOVED***opencode/pegasus-frontend/`

---

## 3. Technology Stack

| Component | Choice |
|---|---|
| **Framework** | Qt 6 / QML + PySide6 (Python backend) |
| **Target Platform** | Linux x86_64, Xorg, optimized for Intel J5005 / UHD 605 |
| **Emulator** | RetroArch via Flatpak (`flatpak run org.libretro.RetroArch --fullscreen -L <core> <rom>`) |
| **Steam** | Steam Flatpak, launch via `xdg-open steam://rungameid/<id>` |
| **Moonlight** | Moonlight Flatpak (`com.moonlight_stream.Moonlight`), CLI for list/stream, Apollo/Sunshine host |
| **Gamepad Input** | `evdev` → synthetic `QKeyEvent` injection (Pegasus Frontend pattern) |
| **Browser** | Brave via Flatpak, dedicated `--user-data-dir` inside flatpak sandbox |
| **Browser Extension** | Manifest V3 Chromium extension for gamepad control in Plex Web |
| **Config** | JSON at `***REMOVED***.config/htpcstation/config.json` |
| **Resolution** | 1920×1080 fullscreen, `vpx()` scaling function (base 1280×720) |
| **Python** | 3.10+ |
| **Plex Auth** | OAuth PIN flow via plex.tv (no manual token entry) |
| **Plex API** | plex.tv for server discovery/user switching; local server for library data |

---

## 4. Codebase Structure

```
htpcstation/
  main.py                              # Entry point, PySide6 engine, context properties, font loading,
                                       # keyboard/gamepad detection, window hide/show on process launch
  .gitignore                           # __pycache__/, *.pyc, *.pyo
  assets/
    fonts/
      NotoEmoji-Regular.ttf            # Bundled emoji font (879KB, OFL license) — loaded but Qt
                                       # doesn't reliably use it as fallback (see gotchas)
  backend/
    __init__.py
    browser_launcher.py                # Brave kiosk launcher, dedicated user-data-dir, extension deploy
    config.py                          # JSON config, 20 system defaults, all setters auto-save
    controller_mapping.py              # Controller mapping config: load/save, default mapping, evdev lookup
    gamepad.py                         # evdev → QKeyEvent injection, auto-repeat, hotplug, raw mode
    gamelist.py                        # gamelist.xml parser, write_game_stats()
    keys.py                            # Semantic key abstraction, input source tracking, button layout
    launcher.py                        # QProcess emulator launcher, async signal-based start
    library.py                         # GameLibrary QObject: models, collections, sort, launch, favorites
    models.py                          # Game and System dataclasses
    plex_account.py                    # plex.tv API client: OAuth, server discovery, home users, user switching
    plex_client.py                     # Plex Media Server HTTP client (requests)
    plex_library.py                    # PlexLibrary QObject: threaded data loading, models, sort/filter,
                                       # server discovery, user switching, browser launch
    plex_models.py                     # PlexMovie, PlexShow, PlexSeason, PlexEpisode dataclasses
    poster_cache.py                    # Thread-safe poster downloader, SHA256 hash filenames
    moonlight_artwork.py               # Artwork cache: Steam Store lookup, CDN download, manual overrides
    moonlight_client.py                # Moonlight CLI wrapper: list_apps(), MoonlightLauncher (QProcess)
    moonlight_config.py                # Shared Moonlight directory helper (***REMOVED***.config/htpcstation/moonlight/)
    moonlight_library.py               # MoonlightLibrary QObject: two-phase refresh, models, launch
    moonlight_models.py                # MoonlightHost, MoonlightApp dataclasses
    moonlight_parser.py                # Moonlight QSettings config parser, host discovery, TCP probe
    moonlight_play_history.py          # Play timestamp recording/reading (play_history.json)
    network_monitor.py                 # NetworkMonitor QObject: periodic connectivity check, online property
    settings_manager.py                # SettingsManager QObject: wraps Config for QML access, OAuth
    steam_config.py                    # Shared Steam directory helper (***REMOVED***.config/htpcstation/steam/)
    steam_library.py                   # SteamLibrary QObject: models, sort, launch, recently played
    steam_models.py                    # SteamGame dataclass
    steam_parser.py                    # ACF/VDF parser, game discovery, artwork resolution + caching
  extension/                           # Chromium browser extension (Manifest V3)
    manifest.json                      # Extension manifest, content scripts on all URLs
    content.js                         # Gamepad API polling loop, edge detection, auto-repeat, Start+Select combo
    generated_mapping.js               # Auto-generated button mapping (written at deploy time)
    mappings/
      default.js                       # No-op fallback mapping for non-Plex sites
      index.js                         # Site matcher: selects mapping based on URL path
      plex.js                          # Plex Web mapping: player controls, virtual focus cursor,
                                        # popup/dropdown navigation, focus stack, stale focus recovery,
                                        # auto-user-select, auto-play (~867 lines, includes TEMP debug overlay)
  qml/
    main.qml                           # ApplicationWindow, vpx(), QuitDialog
    Theme.qml                          # Singleton: colors, fonts, animation durations
    qmldir                             # Singleton registration
    components/
      ClockDisplay.qml                 # HH:MM clock, 1s timer
      FocusRing.qml                    # Reusable focus indicator
      NetworkIndicator.qml             # Canvas-drawn WiFi icon (online/offline)
      QuitDialog.qml                   # Modal quit confirmation
      SettingButton.qml                # Action button row for settings
      SettingSelect.qml                # Cycle-through selector row for settings (server/user picker)
      SettingSlider.qml                # Numeric slider row for settings
      SettingTextInput.qml             # Text input row for settings (with edit mode)
      SettingToggle.qml                # Boolean toggle row for settings
    screens/
      HomeScreen.qml                   # Tab bar (Retro Games/PC Games/Watch/Settings), content loader
      RetroGamesScreen.qml             # System list + game grid + detail view (3-state) for ROMs
      GameGridView.qml                 # Scrollable game grid with screenshots, sort overlay
      GameDetailView.qml               # Game metadata, video snap playback, launch/favorite
      PcGamesScreen.qml                # Source list + game grid + detail view (3-state) for Steam/PC
      SteamGameGrid.qml                # Steam game poster grid with sort overlay
      SteamGameDetail.qml              # Steam game metadata, launch action
      MoonlightAppGrid.qml             # Moonlight app poster grid with sort overlay
      MoonlightAppDetail.qml           # Moonlight app detail, poster, stream action
      RecentlyPlayedGrid.qml           # Unified Steam+Moonlight recently played grid with source badges
      RecentlyPlayedDetail.qml         # Recently played detail with source badge and launch
      WatchScreen.qml                  # Plex library list + movie/show grids + detail views
      PlexMovieGrid.qml                # Movie poster grid, infinite scroll, sort/filter overlay
      PlexMovieDetail.qml              # Movie metadata, poster, play action
      PlexShowGrid.qml                 # TV show poster grid, infinite scroll, sort/filter overlay
      PlexOnDeckGrid.qml               # Continue Watching grid with progress bars
      PlexShowDetail.qml               # Show metadata, horizontal season tabs, episode list
      ControllerMappingDialog.qml       # Full-screen controller mapping dialog (14 inputs)
      SettingsScreen.qml               # 6-section settings menu (Games, Plex, Browser, Moonlight, Controller, UI)
  tests/
    conftest.py                        # Session-scoped QCoreApplication fixture
    test_gamelist_parser_fixes.py      # 7 tests
    test_emulator_launch.py            # 24 tests
    test_collections.py                # 22 tests
    test_filter_sort.py                # 12 tests
    test_plex_backend.py               # 191 tests
    test_plex_account.py               # 45 tests
    test_browser_launch.py             # 31 tests
    test_settings_backend.py           # 99 tests
    test_video_snap.py                 # 5 tests
    test_steam.py                      # 95 tests
    test_controller_mapping.py         # 38 tests
    test_auto_mapping.py               # 31 tests
    test_moonlight_parser.py           # 30 tests
    test_moonlight_client.py           # 24 tests
    test_moonlight_library.py          # 119 tests
    test_moonlight_artwork.py          # 36 tests
    test_moonlight_play_history.py     # 20 tests
    test_network_monitor.py            # 13 tests
```

---

## 5. What's Been Built

### M0 — Shell ✅
- Fullscreen PySide6 + QML application
- Home screen with tab navigation: Retro Games, PC Games, Watch, Settings
- Gamepad input via evdev (D-pad, face buttons, triggers, bumpers)
- Keyboard fallback (arrow keys, Enter, Escape, F-keys)
- Semantic key abstraction (`keys.isAccept()`, `keys.isCancel()`, etc.)
- Auto-repeat on held buttons (500ms initial, 80ms repeat)
- Visible focus ring on all navigable elements
- Animated screen transitions (slide-in, 250ms)
- 24-hour clock display (top-right)
- Quit dialog (Start button or Escape from tab bar)
- Focus save/restore across dialog open/close
- D-pad Down from tab bar enters content area

### M1 — Retro Games (ROMs) ✅
- Config system: JSON config with ROM directory, RetroArch flatpak command, per-system core mapping, 20 built-in system defaults
- Gamelist parser: parses `gamelist.xml` per system, resolves relative `<image>` and `<video>` paths
- System list view: navigable list of discovered platforms with game counts
- Game grid view: scrollable grid with screenshot artwork, async image loading
- Game detail view: full metadata, video snap playback (MediaPlayer + VideoOutput, 1.5s delay, looping, muted), star rating, scrollable description
- Emulator launch: async QProcess-based, `flatpak run org.libretro.RetroArch --fullscreen -L <core> <rom>`
- Play stats write-back: updates `lastplayed`, `playcount`, `gametime`, `favorite` in gamelist.xml
- Favorite toggle: X button, persists to XML, toast notification (2-second auto-dismiss)
- Collections: Favorites, Last Played (50 most recent), All Games — virtual systems at top of list, game counts update in real-time
- Sort: A-Z, Z-A, Recent — Y button opens sort overlay
- Left/Right in game detail navigates to prev/next game
- Stale model guard: `_on_process_finished` skips QML notification if user navigated away during gameplay

### M2 — Plex ✅
- **OAuth login:** PIN-based OAuth flow via `PlexAccount.create_pin()` and `check_pin()`. "Sign in with Plex" button in Settings opens the Plex auth page in the browser; QTimer polls every 2s for up to 120s until the auth token arrives. No manual token entry needed.
- **Server discovery:** Automatic via plex.tv resources API (`PlexAccount.get_resources()`). Connection URL selection prefers local direct IP > plex.direct > relay.
- **User switching:** Home users listed via plex.tv API (`PlexAccount.get_home_users()`). Selected user's token obtained via `switch_user()`. Admin token used for server API calls (managed users lack direct server access); user-specific token used for browser deep links only.
- **Content restrictions:** Managed users' `restrictionProfile` (little_kid, older_kid, teen) is mapped to allowed content ratings. Server-side `contentRating` filter applied to all library queries so managed users only see age-appropriate content.
- **Continue Watching:** `PlexOnDeckGrid.qml` displays in-progress items with poster images, titles (show name + episode title for episodes), and progress bars (`viewOffset/duration`). Hidden for managed users (server rejects managed user tokens for on-deck endpoint — Plex platform limitation).
- **PlexAccount client** (`backend/plex_account.py`): plex.tv API for OAuth, server discovery, home user listing, user switching, token validation. Old `/api/` endpoints use XML responses and token-as-query-parameter. OAuth methods are `@staticmethod` (no token needed).
- Plex API client: libraries, movies, shows, seasons, episodes, on-deck, identity
- Data models: PlexMovie, PlexShow, PlexSeason, PlexEpisode with parsing helpers
- Poster cache: thread-safe downloader, SHA256 hash filenames, `***REMOVED***.config/htpcstation/poster_cache/`
- PlexLibrary QObject: threaded data loading (ThreadPoolExecutor), progressive poster loading, server discovery, user switching, lazy reconnect, content rating filtering
- Watch screen: library list with "Plex" header, Continue Watching, Movies, TV Shows, DVR
- Movie grid: poster grid with infinite scroll (50 per page), portrait cells
- Movie detail: poster, metadata (studio, rating, score, runtime, genre, director, cast), tagline, synopsis
- TV show grid: poster grid with infinite scroll (50 per page), episode progress indicators
- TV show detail: show metadata + horizontal season tabs + episode list with watched indicators (●/○/◐)
- Plex sort & filter: server-side sort (A-Z, Z-A, Recently Added, Year, Rating) + genre filter via Y button
- **Browser launch:** Deep-link to `app.plex.tv` with user token. Auto-user-select and auto-play via browser extension. Dedicated Brave instance with isolated `--user-data-dir`.
- Window hide/show: HTPC Station hides when browser/emulator launches, restores on exit
- Left/Right in movie detail navigates to prev/next movie
- Poster images display in detail views (cached during `getMovie()`/`getShow()`)
- **Live TV:** "Live TV" entry in the Plex library list. Selecting it launches Plex Web at `#!/live-tv` (program guide). Always visible when server is connected. Supports HDHomeRun tuners via Plex DVR.

### M3 — Steam (PC Games) ✅
- **ACF/VDF parser** (`backend/steam_parser.py`): Recursive descent parser for Valve Data Format. `discover_steam_games()` scans Flatpak (`***REMOVED***.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/`) and native (`***REMOVED***.steam/steam/steamapps/`, `***REMOVED***.local/share/Steam/steamapps/`) paths.
- **Game filtering:** Excludes non-game entries (Proton, Steam Linux Runtime, Steamworks Redistributables, incomplete installs with StateFlags ≠ 4).
- **Artwork resolution:** Custom override (`***REMOVED***.config/htpcstation/steam/artwork_custom/<appid>.<ext>`) → HTPC cache (`artwork_scraped/<appid>.jpg`) → local Steam cache (`appcache/librarycache/{appid}/`) → Steam CDN download (saved to `artwork_scraped/`). Always returns a local file path, never a URL. Works offline after first download.
- **SteamLibrary QObject** (`backend/steam_library.py`): `SteamSourceListModel` (source list, extensible for GOG/Epic) and `SteamGameListModel` (game grid). Slots: `refresh()`, `getGame(index)`, `launchGame(appId)`, `selectSource(source)`, `sortGames(sortKey)`.
- **Launch:** `xdg-open steam://rungameid/{appId}` via `QProcess.startDetached()` (fire-and-forget). HTPC Station does not hide/minimize — the game takes focus and HTPC Station sits behind it. When the game exits, the window manager returns focus automatically.
- **PC Games tab:** "PC Games" tab at index 1 (between "Retro Games" and "Watch"). `PcGamesScreen.qml` with 3-state view (sources → games → detail), following the same pattern as `RetroGamesScreen.qml`.
- **SteamGameGrid.qml:** Portrait poster grid (160×240), text-only fallback for missing artwork, sort overlay (A-Z, Z-A, Recent).
- **SteamGameDetail.qml:** Game metadata (name, install dir, size formatted as GB/MB, last played date), launch button, prev/next navigation.
- **Tab rename:** "Games" → "Retro Games", `GamesScreen.qml` → `RetroGamesScreen.qml`.

### M4 — Moonlight ✅
- **Moonlight integration:** Moonlight is installed as Flatpak (`com.moonlight_stream.Moonlight`). HTPC Station wraps its CLI for app enumeration and streaming launch. Pairing is handled by Moonlight's own GUI (launched via "Open Moonlight" in Settings).
- **Host discovery:** Reads paired hosts from Moonlight's QSettings INI config at `***REMOVED***.var/app/com.moonlight_stream.Moonlight/config/Moonlight Game Streaming Project/Moonlight.conf`. `discover_moonlight_hosts()` in `backend/moonlight_parser.py` parses the `[hosts]` section, grouping by numeric prefix. Fields are all lowercase (`hostname`, `localaddress`, `remoteaddress`, `manualaddress`, `uuid`). `customname=false` is treated as "no custom name" (not the string "false").
- **Host availability:** TCP probe on port 47984 (GameStream HTTPS API) via `check_host_available()` with 2s timeout.
- **Two-phase refresh:** Phase 1 (synchronous, ~instant): discovers paired hosts from local config file, auto-selects host if needed, emits `hostsChanged` so "Moonlight Games (Loading...)" appears in the source list immediately. Phase 2 (threaded via `ThreadPoolExecutor`): TCP probes the selected host, runs `flatpak run com.moonlight_stream.Moonlight list <host>` to enumerate apps, resolves artwork. Emits `hostsChanged` again with real app count.
- **Single source entry:** PC Games source list shows one "Moonlight Games" entry (not per-host). Apps come from the host selected in Settings. Source key is `"moonlight"`.
- **App enumeration:** `list_apps()` in `backend/moonlight_client.py` runs `moonlight list <host>` via `subprocess.run` with 10s timeout. Parses stdout (one app name per line), ignores stderr (SDL/Qt noise). Returns empty list on any error.
- **Artwork cache:** `backend/moonlight_artwork.py` resolves poster images for Moonlight apps:
  - **Cache location:** `***REMOVED***.config/htpcstation/moonlight/artwork_scraped/` (auto-downloaded) and `artwork_custom/` (user overrides)
  - **Steam Store lookup:** App name searched via `store.steampowered.com/api/storesearch/`; first result's app ID used to download poster from Steam CDN (`library_600x900_2x.jpg`). Downloaded atomically (temp file → rename).
  - **Manual overrides:** Drop `<slug>.<ext>` into `***REMOVED***.config/htpcstation/moonlight/artwork_custom/`. Created automatically on first run. Files in `artwork_custom/` always take priority.
  - **Slug convention:** Lowercase the app name, replace non-alphanumeric characters with hyphens, collapse multiple hyphens. Examples: "Steam Big Picture" → `steam-big-picture.jpg`, "Divinity: Original Sin II" → `divinity-original-sin-ii.jpg`.
  - **Metadata index:** `artwork_index.json` tracks each app's slug, Steam app ID, source (steam/manual/none), filename, and timestamp. Prevents redundant API calls on subsequent launches.
- **Play history:** `backend/moonlight_play_history.py` records launch timestamps to `***REMOVED***.config/htpcstation/moonlight/play_history.json`. Updated on each `launchApp()` call. Used for "Recently Played" source in PC Games.
- **MoonlightLibrary QObject** (`backend/moonlight_library.py`): `MoonlightAppListModel` with `name`, `hostUuid`, `imagePath`, `lastPlayed` roles. Slots: `refresh()`, `getApp(index)` (returns `name`, `hostAddress`, `hostName`, `hostUuid`, `imagePath`, `lastPlayed`), `launchApp(hostAddress, appName)`, `launchGui()`, `getPairedHosts()`, `setSelectedHost(uuid)`, `sortApps(sortKey)`. Properties: `appsModel`, `loading` (bool, True during Phase 2), `hostOnline` (bool, reflects TCP probe result).
- **MoonlightAppGrid.qml:** Portrait poster grid (160×240) matching Steam card structure. Poster image when `imagePath` available; text-only placeholder otherwise. Sort overlay (A-Z, Z-A).
- **MoonlightAppDetail.qml:** Left-side poster (30% width) matching Steam detail layout. Fallback rectangle with app name when no image. Host name metadata on the right. Stream action.
- **Launch:** `flatpak run com.moonlight_stream.Moonlight stream <host> "<app>"` via `MoonlightLauncher` (QProcess-based, async signal-based start). HTPC Station hides during streaming, restores on exit (same pattern as emulator/browser launch).
- **Settings:** Moonlight section with: Moonlight Command (text input, default `flatpak run com.moonlight_stream.Moonlight`), Host selector (cycle through paired hosts, same UX as Plex User selector), "Open Moonlight" button (launches Moonlight GUI for pairing). Host selection persisted as `moonlight.host_uuid` in config.json.
- **Config:** `moonlight` section in config.json with `command` and `host_uuid` fields.

### M5 — Home Screen (partial) ✅
- **PC Games "Recently Played" source:** Unified source entry at the top of the PC Games source list combining Steam and Moonlight titles sorted by last played time (capped at 20). Each tile has a colored source badge in the top-left corner: blue "S" for Steam, orange "M" for Moonlight. Moonlight play timestamps recorded on launch via `play_history.json`. Steam `lastPlayed` comes from ACF manifests. Simplified detail view with launch dispatch to the correct backend.
- **Network status indicator:** Canvas-drawn WiFi icon (`NetworkIndicator.qml`) next to the clock in the top-right. 3 concentric arcs + dot. Solid in `Theme.colorText` when online, dimmed in `Theme.colorTextDim` with diagonal strikethrough in `Theme.colorPrimary` when offline. `NetworkMonitor` QObject checks connectivity every 30s via TCP probe to `1.1.1.1:53`. Toggle in Settings → User Interface to show/hide.
- **Graceful offline state:** Moonlight source shows "Unavailable" (in accent color) when host is offline, with helpful message in the grid ("Host unavailable — check that your streaming PC is powered on"). `hostOnline` property on `MoonlightLibrary` reflects TCP probe result. `OfflineRole` on `SteamSourceListModel`. Plex offline handling audited and confirmed solid.
- **Steam artwork caching:** Steam poster images now cached locally at `***REMOVED***.config/htpcstation/steam/artwork_scraped/<appid>.jpg`. Downloaded from CDN on first access, served from disk thereafter. Works offline. Custom overrides in `artwork_custom/<appid>.<ext>`. Never returns a URL — always a local file path.
- **Moonlight config directory refactor:** All Moonlight data consolidated under `***REMOVED***.config/htpcstation/moonlight/` with `artwork_scraped/`, `artwork_custom/`, `artwork_index.json`, and `play_history.json`. Shared directory helper in `backend/moonlight_config.py`.

### Browser Gamepad Extension ✅
- **Manifest V3 Chromium extension** at `htpcstation/extension/`
- **Gamepad API polling:** `requestAnimationFrame` loop, edge detection for button presses, auto-repeat (400ms initial, 100ms repeat) for D-pad only
- **Auto-generated button mapping:** `generated_mapping.js` is written at extension deploy time from the stored controller mapping config. Translates evdev codes to Web Gamepad API button indices using device capabilities (sorted button/axis order). Action names are translated to match content.js expectations (e.g., `dpad_up` → `up`, `left_shoulder` → `leftBumper`). Button layout (standard/alternate) is applied at generation time to swap accept/cancel. Falls back to standard gamepad defaults if no mapping exists.
- **Start+Select combo:** Pressing Start and Select simultaneously closes the browser. Detected at the evdev level in `gamepad.py` (not in the extension — `window.close()` is restricted in kiosk mode). `GamepadManager.startSelectCombo` signal triggers `browser_launcher.kill()` which uses `flatpak kill <app_id>` for Flatpak browsers to reliably terminate the sandboxed process and all children. Combo detection suppresses individual button actions until both are released.
- **Analog stick deadzone:** ±0.3, converted to digital directional events
- **Site-aware mapping system:** hostname/path-based dispatch, extensible to future sites
- **Plex Web mapping:**
  - Player mode: D-pad navigates player control bar buttons via virtual focus cursor (with `showPlayerControls()` mouse-move simulation to reveal hidden controls), accept=click focused control or play/pause, cancel=clear focus or close player, X=play/pause, L2/R2=seek back/forward, Y=fullscreen
  - Navigation mode: virtual focus cursor with spatial navigation, accept=click, cancel=escape, Start=exit
  - **Modal support:** When a modal dialog is open (e.g., "Resume Playback"), input routes to navigation mode regardless of player state. D-pad navigates modal options, accept selects, cancel closes.
  - **Player popup/dropdown navigation:** Popup panels (Playback Settings, Chapter Select, Play Queue) and Popper.js dropdown menus are fully navigable with the gamepad. D-pad navigates within the topmost overlay layer; accept clicks; cancel closes the layer and restores focus to the element that opened it. Focus stack tracks layer transitions. Stale focus recovery handles React button swaps (e.g. Repeat/RepeatOne, Play/Pause).
  - **TEMP debug overlay:** An on-screen debug overlay (`__htpc-debug` div, green text on black background) and `dbg()` calls are present in `plex.js` for kiosk-mode debugging. These should be removed when debugging is complete.
- **Auto-user-select:** Reads `htpc_user` from URL, polls for `.user-select-modal`, clicks matching user tile, re-navigates to original deep link after 1.5s
- **Auto-play:** Polls for `[data-testid="preplay-play"]` button, clicks it. Triggers on both page load and `hashchange` events (SPA navigation).
- **Extension deployment:** Copied to `***REMOVED***.var/app/com.brave.Browser/config/htpcstation-extension/` before each launch (flatpak sandbox access)
- **Flatpak gamepad access:** Browser launcher automatically applies `flatpak override --user <app_id> --filesystem=/run/udev:ro` to grant the Flatpak browser access to gamepad devices via the Web Gamepad API. Without this, Chromium-based Flatpak browsers cannot enumerate gamepads.

### Settings UI ✅
- SettingsManager QObject wrapping Config with Q_PROPERTYs and Slots
- 6 sections: Games, Plex, Browser, Moonlight, Controller, User Interface
- Reusable components: SettingTextInput (with edit mode), SettingToggle, SettingButton, SettingSlider, SettingSelect (cycle-through picker)
- Games: ROMs Directory, RetroArch Command, Cores Directory, Rescan Library button
- Plex: Sign in with Plex (OAuth), Test Connection button, Server selector (cycle through discovered servers), User selector (cycle through home users)
- Browser: Browser Command
- Moonlight: Moonlight Command, Host selector (cycle through paired hosts), Open Moonlight button
- Controller: Button Layout selector (Standard/Alternate), Map Controller button, Reset to Default button
- User Interface: Video Snap Autoplay toggle, Video Snap Delay slider (0-5000ms, 100ms steps), Network Indicator toggle
- All changes auto-save to config.json
- Per-system core editor: placeholder ("Coming soon")
- Server/user selection uses `optionsProvider` function (fetches fresh data on each A press, not a static binding)
- `selectServer`/`selectUser` save config and invalidate client without blocking (lazy reconnect on next `refresh()`)

### Input Source Detection ✅
- `Keys` object tracks `useGamepadLabels` property (bool) and `buttonLayout` property ("standard"/"alternate")
- GamepadManager calls `keys.setGamepadInput()` on every injected key press
- Event filter detects `spontaneous()` keyboard events → `keys.setKeyboardInput()`
- All action hint bars use dynamic label properties (`keys.acceptLabel`, `keys.cancelLabel`, `keys.context1Label`, `keys.context2Label`) that update based on button layout setting
- 20 hint bar locations updated across all detail views, grid headers, sort overlays, and dialogs
- Button layout setting swaps both display labels AND functional mapping (which physical button triggers accept vs cancel)

### M6 — Hardening (partial) ✅
- **Async QProcess start:** Replaced blocking `waitForStarted(3000)` with signal-based flow (`QProcess.started` + `QProcess.errorOccurred`) in both `Launcher` and `BrowserLauncher`
- **Stale model guard:** `_on_process_finished` compares stored model reference to current model; skips QML notification if user navigated away during gameplay
- **Collection game counts:** `_rebuild_collections()` rebuilds `SystemListModel` and emits `systemsModelChanged` so Favorites/Last Played counts update immediately
- **Test config isolation:** Fixed `TestSettingsManagerSetters._make_manager()` writing to real `***REMOVED***.config/htpcstation/config.json` (was wiping Plex credentials on every test run)

---

## 6. Gamepad Controls

Gamepad button mapping is fully configurable via Settings → Controller → "Map Controller". The mapping is stored in `***REMOVED***.config/htpcstation/controller_mapping.json` and auto-generates the browser extension mapping at deploy time.

**Default mapping (matches standard layout, A=East):**

| Physical Button | Default evdev Code | Qt Key | Semantic Action |
|---|---|---|---|
| Face East (Accept) | BTN_EAST (305) | Key_Return | Accept / confirm / launch |
| Face South (Cancel) | BTN_SOUTH (304) | Key_Escape | Cancel / back |
| Face North | BTN_NORTH (307) | Key_F1 | Context action 1 (favorite) |
| Face West | BTN_WEST (308) | Key_F2 | Context action 2 (sort) |
| Start | BTN_START (315) | Key_F10 | Quit dialog |
| Select | BTN_SELECT (314) | Key_F9 | Secondary menu |
| Left Shoulder | BTN_TL (310) | Key_PageUp | Previous tab |
| Right Shoulder | BTN_TR (311) | Key_PageDown | Next tab |
| Left Trigger | ABS_Z (2) | Key_Home | Page scroll up |
| Right Trigger | ABS_RZ (5) | Key_End | Page scroll down |
| D-pad | ABS_HAT0X/Y (16/17) | Key_Up/Down/Left/Right | Navigation |
| Start + Select | — | — | Close browser (Alt+F4 equivalent) |

**Button Layout setting** (Settings → Controller → Button Layout):
- **Standard (A=East):** Accept=A, Cancel=B, Context1=X, Context2=Y — matches controllers where A is on the east face position
- **Alternate (A=South):** Accept=B, Cancel=A, Context1=Y, Context2=X — matches controllers where A is on the south face position
- This swaps both the display labels AND the functional mapping (which physical button triggers accept vs cancel)

**Controller mapping dialog:**
- Walks through 14 inputs sequentially using cardinal directions (Face Button East, Face Button South, etc.) to avoid layout confusion
- Records raw evdev button/axis codes via raw mode (gamepad stops injecting keys during mapping)
- Duplicate detection prevents mapping the same button twice
- Skippable inputs (shoulders, triggers) auto-skip after 5 seconds if no input
- Auto-saves on completion — no confirmation button needed (avoids A/B swap confusion)
- Device capabilities recorded alongside mapping for browser extension auto-generation

**Note:** The user's 8BitDo Micro in D-input mode reports D-pad as ABS_X/ABS_Y (0-255 range) instead of ABS_HAT0X/Y (-1/0/1). The mapping system normalizes axis values to -1/0/1 using the axis range, handling both hat and analog D-pad styles transparently.

---

## 7. Config File Structure

Location: `***REMOVED***.config/htpcstation/config.json`

```json
{
  "rom_directory": "/path/to/ROMs",
  "retroarch": {
    "command": "flatpak run org.libretro.RetroArch",
    "cores_directory": "***REMOVED***.var/app/org.libretro.RetroArch/config/retroarch/cores"
  },
  "systems": {
    "gb": { "display_name": "Game Boy", "core": "gambatte_libretro.so", "extensions": [".gb"] },
    ...20 systems total...
  },
  "plex": {
    "token": "<plex.tv_token>",
    "server_id": "<machine_identifier>",
    "user_id": 0
  },
  "browser": {
    "command": "flatpak run com.brave.Browser"
  },
  "moonlight": {
    "command": "flatpak run com.moonlight_stream.Moonlight",
    "host_uuid": "1939F722-9A5D-EA2F-9787-80DD39630D42"
  },
  "ui": {
    "video_snap_autoplay": true,
    "video_snap_delay_ms": 1500,
    "show_network_indicator": true,
    "button_layout": "standard"
  }
}
```

**Note:** Steam has no config — game discovery is fully automatic from standard Steam install paths. No user configuration needed.
**Note:** Moonlight host pairing is managed by Moonlight's own GUI. HTPC Station reads paired host data from Moonlight's config file.

---

## 8. Gotchas & Lessons Learned

### QML Component ID Shadowing
Setting components (`SettingTextInput`, etc.) originally used `id: root` which shadowed the `ApplicationWindow`'s `root` where `vpx()` is defined. This caused `vpx is not a function` errors. **Fix:** Each component uses a unique id (`textInputRoot`, `toggleRoot`, `buttonRoot`, `sliderRoot`, `selectRoot`). **Rule:** Never use `id: root` in any component — that id belongs to the ApplicationWindow.

### QML Signal Name Conflicts
`signal valueChanged(string newValue)` conflicts with QML's auto-generated `valueChanged` signal from `property string value`. This made the component type "unavailable" and cascaded errors to other screens. **Fix:** Renamed to `signal valueEdited(...)`. **Rule:** Never name a signal `<propertyName>Changed` — QML auto-generates those.

### QML Property Bindings Don't Re-evaluate for API Calls
A QML property binding like `options: plex.getServerList().map(...)` evaluates once at component creation. If the API data changes later, the binding never re-evaluates because none of its QML dependencies changed. **Fix:** Use an `optionsProvider` function property that's called on demand (e.g., on each button press) instead of a static binding.

### QML Type Mismatch: QString to int
Passing a JavaScript value from QML to a Python `@Slot(int)` can fail with "Unable to assign QString to int" if the value comes from a JS object property. **Fix:** Use `parseInt(value)` in QML before passing to the slot. Use `==` instead of `===` for comparisons between values that may be int or string.

### QML Image Source: Local Paths vs URLs
QML `Image.source` needs `"file://"` prefix for local paths but URLs must be passed as-is. When a model role can contain either a local path or a CDN URL, check with `startsWith("http")` before prepending `"file://"`. Without this, URLs become `file://https//...` which fails silently.

### Brave Flatpak Session Accumulation
Brave saves session state on exit. Each `--kiosk <url>` launch adds a tab. Without cleanup, tabs accumulate. **Fix:** Before each launch, clear `Sessions/` and `Session Storage/` directories from the browser profile.

### Brave Flatpak `--user-data-dir` — Revised
The flatpak sandbox restricts filesystem access. Custom `--user-data-dir` paths **outside** the sandbox are silently ignored. **Fix (revised):** Use a dedicated `--user-data-dir` **inside** the flatpak sandbox at `***REMOVED***.var/app/com.brave.Browser/config/htpcstation-browser/`. This creates a completely separate Brave instance that doesn't conflict with personal browsing, ensures kiosk mode and extensions always load (even if Brave is already running), and preserves Plex login across launches.

### Brave Existing Instance Ignores Command-Line Flags
If Brave is already running (personal browsing), launching a new URL joins the existing process. `--kiosk`, `--start-fullscreen`, and `--load-extension` flags are silently ignored. The URL opens as a new tab in the existing window. **Fix:** The dedicated `--user-data-dir` creates a separate Brave process, so flags always apply.

### Brave Focus on Launch
HTPC Station's fullscreen window keeps focus when launching Brave. **Fix:** Hide the HTPC Station window on process launch (`window.hide()`), restore on exit (`window.showFullScreen()`, `window.raise_()`, `window.requestActivate()`).

### Steam Launch: Don't Hide the Window
Steam games are launched via `xdg-open steam://rungameid/<id>` which is fire-and-forget — `xdg-open` exits immediately after handing off to Steam. We cannot track when the game actually exits. Hiding the window (`window.hide()`) removes it from the window manager, making it impossible to return to. Minimizing (`window.showMinimized()`) requires Alt+Tab to return. **Fix:** Don't hide or minimize at all for Steam launches. The game takes focus, HTPC Station sits behind it, and the window manager returns focus automatically when the game exits. No performance cost — Qt stops rendering when the window is obscured.

### Plex User Selection Screen Cannot Be Bypassed via URL
Plex Web always shows the user selection screen for multi-user Plex Home accounts. Passing `X-Plex-Token` in the URL (query string or hash fragment) does not bypass it. The "automatically sign in" feature mentioned in Plex docs is a native app setting, not available in Plex Web. **Fix:** Browser extension auto-clicks the correct user tile by matching the `htpc_user` URL parameter against `.username` text in the `.user-select-modal` DOM.

### Plex Web Loses Deep Link After User Selection
After clicking a user in the Plex Web user selection modal, the app navigates to the home screen and loses the original deep link URL (hash fragment). **Fix:** Extension saves the original URL before clicking the user, waits 1.5s for the transition, then re-navigates via `window.location.href`.

### Plex Web Auto-Play Requires hashchange Listener
The content script runs once at `document_idle`. When the auto-user-select re-navigates, Plex Web handles it as a client-side hash change — the page doesn't reload, so the content script doesn't re-execute. **Fix:** `tryAutoPlay()` listens for `hashchange` events in addition to running on initial page load.

### Plex Old API Endpoints Require Token as Query Parameter
The plex.tv `/api/home/users` and `/api/home/users/{id}/switch` endpoints (no `v2`) reject the `X-Plex-Token` header. The token must be passed as a query parameter (`?X-Plex-Token=...`). These endpoints also return XML, not JSON, regardless of the `Accept` header. **Fix:** `PlexAccount` uses `params={"X-Plex-Token": self._token}` for old endpoints and parses responses with `xml.etree.ElementTree`.

### Plex Managed Users Cannot Access Server Directly
Managed/restricted Plex Home users (e.g., "Kids") get a user-specific token from `switch_user()`, but this token returns 401 when used against the media server API — both as a header and as a query parameter. This applies to ALL server endpoints (`/library/sections`, `/library/onDeck`, etc.). **Fix:** Always use the admin token for server API calls. Content restrictions are enforced server-side via `contentRating` filter parameter on library queries (mapped from the user's `restrictionProfile`). The user-specific token is only used in browser deep links.

### Plex Managed Users Have No On-Deck Access
Because managed user tokens get 401 from the server, there is no way to fetch a managed user's "Continue Watching" data. The admin token's `/library/onDeck` returns only the admin's in-progress items with no user/account identifier. **Fix:** Hide "Continue Watching" entirely for managed users. This is a Plex platform limitation with no known workaround.

### Plex Content Rating Filter Caching
The `_content_rating_filter` must be cached alongside the user token (`_cached_content_rating_filter`). Without caching, the filter is only set on a fresh `switch_user()` call. When the cached token path is used (on subsequent `_setup_client()` calls), the filter would be empty, showing the full catalog. **Fix:** Store and restore `_cached_content_rating_filter` in the same code paths as `_cached_user_token`.

### Plex User Token Caching and Rate Limiting
`switch_user()` returns an ephemeral token. Calling it on every `refresh()` hammers the API and triggers 429 (Too Many Requests). **Fix:** Cache the user token (`_cached_user_id`, `_cached_user_token`, `_cached_user_title`). Only call `switch_user()` when the user ID changes. `selectUser()` clears the cache so the next `_setup_client()` gets a fresh token.

### selectServer/selectUser Must Not Block
`selectServer()` and `selectUser()` originally called `_setup_client()` and `refresh()` synchronously. If the selected server was unreachable, the UI froze for the full connection timeout. **Fix:** These methods only save the config and invalidate the current client. The actual reconnection happens lazily on the next `refresh()` (e.g., when navigating to the Watch tab).

### Gamepad evdev Crash Loop
`InputDevice.read()` returns a generator. The actual `device_read_many` call happens during iteration, not on `.read()`. The `OSError` catch must wrap the entire `for event in events:` loop, not just the `.read()` call.

### VAAPI Decoding Errors
Video snap playback logs harmless VAAPI hardware decoding errors when the iGPU doesn't support the H.264 profile. ffmpeg falls back to software decoding automatically. **Fix:** `os.environ.setdefault("LIBVA_MESSAGING_LEVEL", "0")` in main.py.

### Qt 6 Video Convenience Type
The `Video` QML type didn't render video despite loading the file. **Fix:** Use explicit `MediaPlayer` + `VideoOutput` components instead, with a 100ms+ delay before calling `play()`.

### QML Context Property Null on Startup
QML evaluates bindings during component creation before context properties are set. Any binding that reads `plex.*`, `steam.*`, or `settings.*` will get null on first evaluation. **Fix:** Add null guards (`if (!steam) return`, `plex ? plex.model : null`) in bindings and functions that read context properties eagerly.

### Bundled Emoji Font
NotoEmoji-Regular.ttf is bundled and loaded via `QFontDatabase.addApplicationFont()`, but Qt doesn't reliably use it as a fallback for all emoji glyphs (particularly `🎮`). **Workaround:** Collection display names use plain text (no emoji prefixes). The font file remains bundled for potential future use.

### Moonlight QSettings INI Field Names
The Moonlight config file uses Qt's `QSettings` INI format. Field names are **all lowercase** (`hostname`, `localaddress`, `remoteaddress`, `manualaddress`, `uuid`), not camelCase as one might assume from Qt conventions. The `customname` field stores `"false"` (a boolean string) when no custom name is set — not an empty string. The parser must treat `"false"` and `"true"` as "no custom name." The `address` field does not exist; the primary address must be derived from `manualaddress` → `localaddress` → `remoteaddress`.

### Moonlight CLI Spawns a Qt GUI
`flatpak run com.moonlight_stream.Moonlight list <host>` outputs app names to stdout but also initializes SDL/Qt, emitting warnings to stderr. The `list` command exits after output; the `stream` command is long-running. Stderr must be ignored entirely. The `pair` command blocks waiting for host-side PIN confirmation — it cannot be automated from HTPC Station.

### Moonlight Artwork: Steam Search Accuracy
The Steam Store search API (`storesearch`) returns fuzzy matches. Most game titles match correctly (e.g., "Slime Rancher", "Divinity: Original Sin II"), but non-game apps (e.g., "Desktop") may match incorrect results. Utility apps like "Playnite", "Steam Big Picture", and "Virtual Display" return no results. **Fix:** Users can drop custom artwork into `***REMOVED***.config/htpcstation/moonlight/artwork_custom/<slug>.<ext>` to override or supplement auto-downloaded images.

### Two-Phase Refresh for Perceived Performance
Network-dependent data (host probing, app enumeration) causes multi-second delays. Showing "Loading..." immediately while background work completes dramatically improves perceived responsiveness. The pattern: Phase 1 (synchronous, local data) emits a signal to update the UI instantly; Phase 2 (threaded, network I/O) emits the same signal again when complete. The UI handler reads the current state each time.

### Flatpak Browsers Cannot See Gamepads Without /run/udev
Chromium-based browsers in Flatpak sandboxes cannot enumerate game controllers via the Web Gamepad API because `/run/udev` is not accessible by default. The `devices=all` Flatpak permission is insufficient — the browser needs udev to discover input devices. **Fix:** `browser_launcher.py` applies `flatpak override --user <app_id> --filesystem=/run/udev:ro` before each launch. This is idempotent and only runs for Flatpak browser commands.

### Gamepad Auto-Repeat Timers Leak Into Raw Mode
When entering raw mode for the controller mapping dialog, any currently held button has an active auto-repeat timer. The timer fires `_press_key` directly, bypassing the raw mode check in `_handle_button`. This causes ghost key injections during the mapping flow. **Fix:** `startRawMode()` calls `_release_all_keys()` on every handler to release all pressed keys, stop all repeat timers, and clear D-pad/trigger state. `stopRawMode()` does the same to prevent stale state from carrying over.

### Controller Mapping Dialog Cannot Use Accept/Cancel Buttons
After mapping all inputs, the dialog needs the user to confirm saving. But the A/B button mapping may be swapped until the new mapping is applied — the user would press what they think is "accept" but it triggers "cancel" (discarding the mapping). **Fix:** Auto-save when all inputs are recorded. No confirmation button needed. Shows "Saved!" briefly then auto-closes.

### Browser window.close() Restricted in Kiosk Mode
`window.close()` in the browser extension is silently ignored for kiosk windows (browsers only allow closing windows opened via `window.open()`). Killing the `QProcess` (the `flatpak run` wrapper) also doesn't work — Flatpak spawns the browser as a child process that survives the wrapper's death. **Fix:** Use `flatpak kill <app_id>` which reliably terminates the entire sandboxed process and all its children. For non-Flatpak browsers, fall back to `QProcess.kill()`.

### Browser Extension Action Name Mismatch
The generated mapping used internal action names (`dpad_up`, `left_shoulder`) but `content.js` expected different names (`up`, `leftBumper`). The `isDirectional()` function checked for `"up"/"down"/"left"/"right"`, not `"dpad_up"` etc. **Fix:** Added `_WEB_ACTION_NAMES` translation table in `controller_mapping.py` that maps internal names to content.js names during mapping generation.

### D-Input Mode Reports D-pad as Analog Axes
Some controllers in D-input mode report D-pad as ABS_X/ABS_Y (range 0-255, centered at 127) instead of ABS_HAT0X/ABS_HAT0Y (range -1 to 1). The raw values (0, 127, 255) must be normalized to -1/0/1 using the axis range for both the mapping dialog (recording) and runtime (key injection). Without normalization, the evdev lookup stores wrong values and D-pad directions collide.

### Plex Web Uses Popper.js for Dropdown Menus (Not Radix)
Plex Web renders dropdown menus (quality, audio track, subtitle track) as Popper.js portals inside `#modal-root`. They are detected via `[data-popper-placement]` or `[class*="Menu-menuPortal"]` with `[role="menuitem"]` descendant check to avoid false-positives on tooltips. These are NOT modals — `getActiveModal()` won't find them.

### Plex Player Popup Panels Float Above the Control Bar
Popup panels (Playback Settings, Chapter Select, Play Queue) are absolutely positioned divs, not modals. They use different container classes:
- **Playback Settings:** `AudioVideoStripeContainer-container-*` with `[data-testid="playbackSettingsContainer"]`
- **Chapter Select:** `AudioVideoStripeContainer-container-*` with `VideoChapters-container-*`
- **Play Queue:** `AudioVideoPlayQueue-container-*` (does NOT have `AudioVideoStripeContainer`)
Detection uses `[data-testid="playbackSettingsContainer"]` → `[class*="AudioVideoStripeContainer"]` → `[class*="AudioVideoPlayQueue-container"]` with a visibility check (`getBoundingClientRect()` width/height > 0).

### Plex Class Name Hashes Change Between Versions
Plex Web uses CSS Modules with hashed suffixes (e.g., `AudioVideoStripeContainer-container-mixkS9`). These hashes change between Plex versions. **Rule:** Always use `[class*="prefix"]` partial matching, never exact class names. Prefer `data-testid` attributes where available — they are stable across versions.

### Escape Key Must Be Dispatched on the Overlay Element
Plex's menu handlers listen on the menu container, not on `document`. Dispatching Escape on `document` does nothing. **Fix:** Dispatch Escape on the overlay element itself (or a focused element within it). For dropdowns, dispatch on the dropdown container or the focused menuitem. For popup panels, dispatch on the panel container.

### Bare .click() Doesn't Work on Plex React Buttons
Plex's React event system requires the full pointer/mouse event sequence: `pointerdown` → `mousedown` → `pointerup` → `mouseup` → `click`. A bare `.click()` only fires the click event and misses handlers registered on `pointerdown`/`mousedown`. The events must include `buttons: 1` for down events, `buttons: 0` for up/click events, and bounding rect center coordinates for `clientX`/`clientY` (some handlers validate pointer position).

### Plex React Re-renders Swap DOM Elements on Click
Clicking certain player buttons causes React to replace the DOM element entirely (e.g., `repeatButton` → `repeatOneButton`, `pauseButton` → `resumeButton`). The old element is removed from the DOM. **Fix:** Save the focused element's center coordinates (`lastFocusCX`/`lastFocusCY`) in `setFocus()`. When the focused element is no longer in the DOM, use `document.elementFromPoint()` at the saved coordinates to find the replacement. `getBoundingClientRect()` returns zeros for removed elements — coordinates must be captured BEFORE removal.

### Focus Stack Must Only Push for Layer-Opening Clicks
Every `accept` press was originally pushing to the focus stack, causing stack pollution. When navigating within a popup panel (e.g., clicking a chapter item or quality option), the stack grew with non-layer-opening elements. On cancel, the stack would pop to a stale element instead of the button that opened the panel. **Fix:** Only push when the clicked element has `aria-haspopup` or matches known trigger button `data-testid` values (`videoSettingsButton`, `chaptersButton`, `playQueueButton`, `moreButton`).

### Popup Cancel Fallback Must Identify the Panel Type
The 150ms fallback timer for closing popup panels (when Escape doesn't work) was always clicking `videoSettingsButton` regardless of which panel was open. This caused the wrong panel to toggle. **Fix:** Identify the panel type (Playback Settings vs Chapter Select vs Play Queue) and click the correct toggle button (`videoSettingsButton`, `chaptersButton`, or `playQueueButton`).

### Player Control Bar Scoping Prevents Unwanted Navigation
Without scoping, `getInteractiveElements()` finds elements in the seek bar, volume slider, metadata links, and other non-useful areas of the player. **Fix:** `getPlayerNavigableElements()` restricts navigation to the top bar (`AudioVideoFullPlayer-topBar`) and bottom control bar (`[data-testid="playerControlsContainer"]`) only. Excludes `metadataTitleLink` (navigates away), `mediaDuration` (not actionable), and volume slider (controlled via TV/receiver).

### showPlayerControls() Mouse-Move Can Dismiss Overlays
The `showPlayerControls()` function dispatches a synthetic `mousemove` event to reveal the hidden player control bar. This mouse-move can cause Plex to dismiss an open dropdown or popup panel. **Fix:** Only call `showPlayerControls()` when no popup panel or dropdown is currently open.

### Kiosk Mode Blocks All DevTools Access
In Brave's `--kiosk` mode, Ctrl+Shift+I, Ctrl+Shift+J, F12, and `--auto-open-devtools-for-tabs` are all blocked. `console.log()` output goes to the inaccessible JS console. **Workaround:** Inject a TEMP on-screen debug overlay (`__htpc-debug` div, green text on black background, top-left corner) at the top of `plex.js`. Use `dbg('message')` to write to it. This overlay and all `dbg()` calls should be removed when debugging is complete.

### Artwork Override Ambiguity
When auto-downloaded and user-provided artwork share the same directory and filename, the system cannot distinguish "user replaced the file" from "app downloaded the file." **Fix:** Use separate directories: `artwork_scraped/` for auto-downloaded and `artwork_custom/` for user overrides. Files in `artwork_custom/` always take priority. Both directories are created automatically so users can discover them. This pattern is used for both Moonlight (`***REMOVED***.config/htpcstation/moonlight/`) and Steam (`***REMOVED***.config/htpcstation/steam/`).

---

## 9. Temporary Decisions

These are intentional shortcuts that should be revisited:

| Decision | Location | Why | Future Fix |
|---|---|---|---|
| Plex token in config.json | `config.json` | Plaintext token stored after OAuth | Encrypt or use OS keyring |
| Synchronous `getMovie()`/`getShow()` | `plex_library.py` | Blocks main thread briefly for API call + poster download | Move to threaded worker |
| Synchronous `testPlexConnection()` | `settings_manager.py` | Blocks main thread during connection test | Defer to thread (partially mitigated with `Qt.callLater`) |
| Per-system core editor | `SettingsScreen.qml` | Shows "Coming soon" toast | Build sub-screen with system list and editable cores |
| `--kiosk` + `--start-fullscreen` | `browser_launcher.py` | Both flags used for Brave fullscreen | May only need one; test on other Chromium browsers |
| No Continue Watching for managed users | `plex_library.py` | Managed user tokens get 401 from server on-deck endpoint | Plex platform limitation — no known workaround |
| Auto-user-select 1.5s delay | `extension/mappings/plex.js` | Fixed delay before re-navigating after user selection | Detect navigation completion instead of fixed timeout |
| Synchronous OAuth polling | `settings_manager.py` | `check_pin()` called synchronously in QTimer callback | Move to thread if UI lag is noticeable |
| Steam games not fullscreen | `steam_library.py` | Game fullscreen is controlled by each game's own settings | Investigate Steam Big Picture mode or per-game launch options |
| Moonlight artwork: Steam search only | `moonlight_artwork.py` | Non-game apps (Desktop, Playnite) get wrong or no artwork | Add IGDB/RAWG fallback, or manual metadata entry |
| Moonlight/Steam detail views lack metadata | `MoonlightAppDetail.qml`, `SteamGameDetail.qml` | Only show name, host, install dir — no description/genre/etc. | Scrape from Steam Store API (`appdetails`) and cache locally |

---

## 10. Remaining Milestones

### M5 — Home Screen (remaining items)
- Rich metadata for Moonlight/Steam apps (description, publisher, players, release year) — see deferred items

### M6 — Hardening (remaining items)
- Performance profiling on J5005 reference hardware (60fps, <200MB idle RAM)
- Memory optimization
- Offline graceful degradation
- Autostart documentation (systemd user service vs `.xinitrc`)
- Path matching robustness in `write_game_stats`
- Unit test infrastructure improvements, CI

### Plex Player Gamepad Controls ✅ (popup/dropdown navigation complete, cleanup remaining)
- **Status:** Full player gamepad navigation working — control bar, popup panels, dropdown menus, modals. L2/R2 seek, Start+Select close.
- **Player mode mapping:** D-pad → navigate (scoped to topmost layer), A → click focused element (with focus stack push for layer-opening clicks), B → close topmost layer (dropdown → popup → modal → player → nav), X → play/pause, L2/R2 → seek back/forward, Y → fullscreen, Start+Select → kill browser
- **What works:** Control bar button navigation (play, skip, repeat, shuffle, etc.), Playback Settings panel, Chapter Select panel, Play Queue panel, Popper.js dropdown menus (quality, audio track, subtitle track), Resume Playback modal, L2/R2 seek, Start+Select close, React button swap recovery (Repeat/RepeatOne, Play/Pause)
- **Cleanup needed:**
  - Remove TEMP debug overlay (`__htpc-debug` div injection) and all `dbg()` calls from `plex.js`
  - The debug overlay was necessary because DevTools cannot be opened in kiosk mode (Ctrl+Shift+I, F12 all blocked, `--auto-open-devtools-for-tabs` flag doesn't work in kiosk)
- **Known bug — Minimized player on relaunch:** When user closes the kiosk browser during playback (Alt+F4 / Start+Select), then re-launches the same title from HTPC Station "Continue Watching", Plex opens with the player minimized (mini player bar at bottom, home screen visible behind). The `div#plex` element lacks the `show-video-player` class. A `Player-miniPlayerContainer-*` div contains an `expandPlayerButton` (`data-testid="expandPlayerButton"`) that should be auto-clicked to restore full-screen. The existing `tryAutoPlay()` pattern (polling for a `data-testid` button) could be extended for this. Saved HTML at `***REMOVED***opencode/page.html`.

### Deferred Items (no milestone assigned)
- **Game metadata scraping for Steam and Moonlight detail views:** Automatically fetch description, publisher, developer, players, release year, genre, etc. from Steam Store API (or IGDB/RAWG as fallback). Retro games already have this from gamelist.xml; Steam and Moonlight detail views currently show minimal metadata (name, install dir, host). The Steam Store API (`store.steampowered.com/api/appdetails/?appids=<id>`) returns rich metadata for Steam games. For Moonlight apps, cross-reference the app name against Steam search (same pattern as artwork lookup) to get the Steam AppID, then fetch details. Cache metadata locally (similar to artwork cache). Non-game apps (Desktop, Playnite, etc.) would show no metadata — graceful fallback.
- Detail list view toggle (alternative to grid for games)
- Custom user-defined game collections
- Standalone emulator support (Dolphin, PCSX2)
- Per-system core editor sub-screen in settings
- Plex search
- Mark watched/unwatched in Plex
- On-screen keyboard for 10-foot text input
- Gamepad extension: YouTube, Netflix, and other site mappings
- Plex token encryption or OS keyring storage
- Steam Big Picture mode integration for fullscreen game launches
- GOG Galaxy, Epic Games Store integration under PC Games tab

### v2+ (Out of scope for v1)
- YouTube — `youtube.com/tv` kiosk launch
- Streaming services — Netflix, Hulu, Prime, Max, Disney+, Apple TV+
- TMDB integration for streaming service metadata
- Wayland support
- Pluggable theme system (Theme.qml singleton is designed for this)
- Multi-user profiles / parental controls
- 4K HDR support (1080p is primary target)
- Screensaver

---

## 11. User Preferences (Observed)

- Prefers simple, functional UI over polish
- Sort options for games: A-Z, Z-A, Recent only (no genre sort, no genre filter, no players sort)
- Plex sort: A-Z, Z-A, Recently Added, Year, Rating + genre filter
- Wants confirmation feedback for actions (favorite toggle toast)
- RetroArch launches fullscreen
- No emoji/symbol prefixes on collection names (rendering issues)
- JSON config preferred over TOML for manual editing
- Fedora Linux, flatpak RetroArch, flatpak Brave, flatpak Steam
- Video snap delay: 1500ms
- Keyboard navigation is a first-class citizen (adaptive hint labels)
- Version control via git from this point forward
- Tab naming: "Retro Games" (ROMs), "PC Games" (Steam/GOG/Epic), "Watch" (Plex), "Settings"
- Prefers Chromium/Brave for Plex playback over native players (hardware decoding quality)
- Controller: 8BitDo Micro in D-input mode, does not have analog sticks
- Prefers standard button layout (A=East) — controller mapping configured via Settings
- No proprietary trademarks in code (use "standard"/"alternate" not brand names for button layouts)
- Has multiple Plex servers (owns one, accesses friends' servers)
- Uses Plex Home with multiple users (admin + managed "Kids" profile)
- Wants PC Games tab to follow same layout pattern as Retro Games (system list → grid → detail)
- Dev machine (ThinkPad T460) is lower spec than target (J5005) — good for performance validation
- Has a Sunshine/Apollo host on local network (***REMOVED*** at ***REMOVED***) for Moonlight streaming
- Wants Moonlight to show as single "Moonlight Games" source (not per-host entries)
- Wants host selection in Settings (not in the source list)
- Prefers `custom/` subdirectory for user artwork overrides (clear separation from auto-downloaded)

---

## 12. Architecture Notes for New Agent

### QML Context Properties
Eight Python objects are exposed to QML:
- `keys` — `Keys` instance (semantic key checks, input source tracking, button layout labels)
- `library` — `GameLibrary` instance (ROM data, models, launch, favorites)
- `steam` — `SteamLibrary` instance (Steam game data, models, sort, launch)
- `moonlight` — `MoonlightLibrary` instance (Moonlight host/app data, models, launch, artwork)
- `plex` — `PlexLibrary` instance (Plex data, models, sort/filter, browser launch, server/user management)
- `gamepadManager` — `GamepadManager` instance (raw mode for mapping dialog, device capabilities)
- `networkMonitor` — `NetworkMonitor` instance (periodic connectivity check, online property)
- `settings` — `SettingsManager` instance (config read/write for settings UI, OAuth)

### Steam Architecture
- **`steam_config.py`** — Shared directory helper for `***REMOVED***.config/htpcstation/steam/` with `artwork_scraped/` and `artwork_custom/` subdirs.
- **`steam_parser.py`** — VDF/ACF parser (recursive descent tokenizer), game discovery from multiple Steam install paths, non-game filtering, artwork resolution (custom override → HTPC cache → Steam local cache → CDN download)
- **`steam_models.py`** — `SteamGame` dataclass (app_id, name, install_dir, last_played, size_on_disk, image_path)
- **`steam_library.py`** — `SteamLibrary` QObject with `SteamSourceListModel` (extensible source list, includes "Recently Played" and Moonlight sources) and `SteamGameListModel`. Fire-and-forget launch via `xdg-open`. No window hide/minimize — game takes focus, window manager handles return. `getRecentlyPlayed()` merges Steam + Moonlight titles sorted by recency. `launchRecentGame()` dispatches to correct backend.

### Moonlight Architecture
- **`moonlight_parser.py`** — Parses Moonlight's QSettings INI config file (Flatpak path: `***REMOVED***.var/app/com.moonlight_stream.Moonlight/config/Moonlight Game Streaming Project/Moonlight.conf`). Extracts paired hosts from `[hosts]` section. TCP probe for host availability on port 47984.
- **`moonlight_config.py`** — Shared directory helper for `***REMOVED***.config/htpcstation/moonlight/` with `artwork_scraped/`, `artwork_custom/` subdirs.
- **`moonlight_models.py`** — `MoonlightHost` (name, uuid, addresses, custom_name, display_name property) and `MoonlightApp` (name, host_uuid, image_path, last_played) dataclasses.
- **`moonlight_client.py`** — `list_apps()` wraps `moonlight list <host>` CLI (synchronous, designed for thread pool). `MoonlightLauncher` wraps `moonlight stream <host> "<app>"` via QProcess with signal-based lifecycle.
- **`moonlight_artwork.py`** — Artwork cache at `***REMOVED***.config/htpcstation/moonlight/artwork_scraped/`. Steam Store search API → CDN poster download. Manual overrides in `artwork_custom/`. Metadata index (`artwork_index.json`) prevents redundant API calls.
- **`moonlight_play_history.py`** — Records launch timestamps to `play_history.json`. `record_play()`, `get_last_played()`, `get_all_history()` with atomic writes.
- **`moonlight_library.py`** — `MoonlightLibrary` QObject orchestrator. Two-phase refresh: Phase 1 (synchronous host discovery) → Phase 2 (threaded probe + app enumeration + artwork resolution + play history). Single selected host (from config). `MoonlightAppListModel` with `name`, `hostUuid`, `imagePath`, `lastPlayed` roles. `hostOnline` property reflects TCP probe result. Moonlight hosts injected into Steam's `SteamSourceListModel` via `setMoonlightSources()` as a single "Moonlight Games" entry.

### Plex Architecture
Two separate API layers:
- **`PlexAccount`** (`plex_account.py`) — talks to `plex.tv` for OAuth, server discovery, home user listing, user switching. Uses `/api/v2/` (JSON) for resources/user validation/OAuth and `/api/` (XML) for home users/switching. Token passed as query parameter for old endpoints. OAuth methods (`create_pin`, `check_pin`) are `@staticmethod` — no token needed.
- **`PlexClient`** (`plex_client.py`) — talks to the media server (resolved URL from resources API) for library data, metadata, posters. Always uses the admin token. Supports `contentRating` filter parameter for managed user content restrictions.
- **`PlexLibrary`** (`plex_library.py`) — QObject that orchestrates both. Creates `PlexAccount` from config token, resolves server URL, switches user, creates `PlexClient`. Exposes QML slots for server/user selection. Stores `_active_token` (user-specific) for browser deep links separately from the admin token used by `PlexClient`. Caches user token, title, and content rating filter to avoid repeated API calls. On-deck data skipped for managed users (server rejects their tokens).

### Browser Extension Architecture
- Content scripts injected on all URLs (Manifest V3, `run_at: document_idle`)
- No ES modules — files concatenated in execution order via manifest `js` array: `generated_mapping.js` → `mappings/*.js` → `content.js`
- Global namespace pattern: `window.__htpcGamepadMappings` for mapping registration, `window.__htpcGeneratedMapping` for auto-generated button map
- Site detection: `index.js` checks `window.location.pathname` for `/web/` or `/desktop/`
- Gamepad polling: `requestAnimationFrame` loop in `content.js`, edge detection, auto-repeat for D-pad only
- Auto-generated mapping: `browser_launcher.py` writes `generated_mapping.js` from `controller_mapping.json` at deploy time, translating evdev codes to Web Gamepad API indices
- Extension deployed to `***REMOVED***.var/app/com.brave.Browser/config/htpcstation-extension/` via `shutil.copytree` before each launch
- Flatpak override `--filesystem=/run/udev:ro` applied automatically for gamepad access

### Browser Isolation
- Dedicated `--user-data-dir` at `***REMOVED***.var/app/com.brave.Browser/config/htpcstation-browser/` inside the flatpak sandbox
- Ensures HTPC Station's Brave instance is completely separate from personal browsing
- Kiosk mode, extensions, and command-line flags always apply, even if Brave is already running
- Plex login persists across launches in the dedicated profile
- Session restore files (`Sessions/`, `Session Storage/`) cleared before each launch to prevent tab accumulation

### Focus Management Pattern
- Every screen/component is a `FocusScope` with `enabled: focus`
- Gamepad events are injected as `QKeyEvent`s — QML only sees keyboard events
- `FocusRing.qml` shows on `parent.activeFocus`
- `vpx()` function lives on the `ApplicationWindow` (id: `root`) — child components must NOT shadow this id

### Threading Model
- All UI on the Qt main thread
- Plex API calls via `ThreadPoolExecutor(max_workers=2)` with results delivered via Qt signals
- Moonlight host probing + app enumeration + artwork download via `ThreadPoolExecutor(max_workers=2)` with results delivered via internal Qt signals (`_hostsDiscovered`, `_appsDone`)
- Poster downloads happen on thread pool, `dataChanged` emitted on main thread
- Emulator/browser/Moonlight launch via `QProcess` (async signal-based, non-blocking)
- Steam game discovery is synchronous (ACF files are small local reads)
- Moonlight Phase 1 (host discovery from local config) is synchronous (fast file read)

### Process Lifecycle
- **Emulators/Browser/Moonlight:** `processStarted` signal → `window.hide()`, `processFinished` signal → `window.showFullScreen()` + `raise_()` + `requestActivate()`
- **Steam:** No window management — game takes focus, window manager handles return on game exit
- **Moonlight GUI ("Open Moonlight"):** Same hide/show pattern as streaming — window hides while Moonlight GUI is open for pairing, restores when closed
- **Browser kill (Start+Select):** `GamepadManager.startSelectCombo` signal → `browser_launcher.kill()` → `flatpak kill <app_id>` for Flatpak browsers. Detected at evdev level, not in the extension.
- Browser session files cleared before each launch to prevent tab accumulation
- `launchGame()` (ROMs) sets `_active_game` optimistically; clears on `FailedToStart`

### Task Brief Archive
All task briefs from the implementation are at:
- `***REMOVED***opencode/misc/coding-team/m0-shell/` (tasks 001–004)
- `***REMOVED***opencode/misc/coding-team/m1-games/` (tasks 005–014)
- `***REMOVED***opencode/misc/coding-team/m2-plex/` (tasks 015–020)
- `***REMOVED***opencode/misc/coding-team/deferred-batch-1/` (tasks 021–024)
- `***REMOVED***opencode/misc/coding-team/settings/` (tasks 025–026)
- `***REMOVED***opencode/misc/coding-team/m6-hardening-pullforward/` (tasks 001–003)
- `***REMOVED***opencode/misc/coding-team/browser-gamepad-extension/` (tasks 001–004)
- `***REMOVED***opencode/misc/coding-team/plex-server-discovery/` (tasks 001–004)
- `***REMOVED***opencode/misc/coding-team/plex-polish/` (tasks 001–003)
- `***REMOVED***opencode/misc/coding-team/m3-steam/` (tasks 001–003)
- `***REMOVED***opencode/misc/coding-team/m4-moonlight/` (tasks 001–012)
- `***REMOVED***opencode/misc/coding-team/plex-show-pagination/` (task 001)
- `***REMOVED***opencode/misc/coding-team/plex-live-tv/` (task 001)
- `***REMOVED***opencode/misc/coding-team/m5-home-screen/` (tasks 001–006)
- `***REMOVED***opencode/misc/coding-team/plex-resume-modal/` (task 001)
- `***REMOVED***opencode/misc/coding-team/controller-mapping/` (tasks 001–003)
- `***REMOVED***opencode/misc/coding-team/plex-player-popups/` (tasks 001–005)

---

### Custom Artwork — User Guide

**Moonlight apps** — `***REMOVED***.config/htpcstation/moonlight/artwork_custom/`
- Files named `<slug>.<ext>` where slug = app name lowercased, non-alphanumeric → hyphens
- Examples: `desktop.jpg`, `steam-big-picture.png`, `playnite.jpg`, `divinity-original-sin-ii.jpg`

**Steam games** — `***REMOVED***.config/htpcstation/steam/artwork_custom/`
- Files named `<app_id>.<ext>` where app_id = Steam application ID (found in Steam Store URLs)
- Examples: `440.jpg` (TF2), `570.jpg` (Dota 2)

Both directories are created automatically on first run. Custom files always take priority over auto-downloaded artwork. Supported formats: jpg, jpeg, png, gif, webp. Changes picked up on next tab navigation or restart.

---

*End of resume document. Start the next session by reading this file and the original proposal at `***REMOVED***opencode/proposal.md`.*
