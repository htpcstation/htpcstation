# HTPC Station — Project Resume Document (Checkpoint 2)

> Hand this file to a fresh agent context to resume development without losing progress.
> Previous checkpoint: Checkpoint 1 (after M0+M1). This checkpoint covers all work through Settings UI.

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
- **Tests:** 224 passing (`python3 -m pytest tests/ -q`)
- **Run:** `cd ***REMOVED***opencode/htpcstation && python3 main.py`
- **Dependencies:** `pip install PySide6 evdev requests`

**Reference data:**
- ROMs: `***REMOVED***opencode/ROMs/` (3 systems: gb, ngpc, sega32x with gamelist.xml, screenshots, videos)
- ES-DE reference: `***REMOVED***opencode/es-de/`
- Pegasus reference: `***REMOVED***opencode/pegasus-frontend/`

---

## 3. Technology Stack

| Component | Choice |
|---|---|
| **Framework** | Qt 6 / QML + PySide6 (Python backend) |
| **Target Platform** | Linux x86_64, Xorg, optimized for Intel J5005 / UHD 605 |
| **Emulator** | RetroArch via Flatpak (`flatpak run org.libretro.RetroArch --fullscreen -L <core> <rom>`) |
| **Gamepad Input** | `evdev` → synthetic `QKeyEvent` injection (Pegasus Frontend pattern) |
| **Browser** | Brave via Flatpak (`flatpak run com.brave.Browser --kiosk --start-fullscreen <url>`) |
| **Config** | JSON at `***REMOVED***.config/htpcstation/config.json` |
| **Resolution** | 1920×1080 fullscreen, `vpx()` scaling function (base 1280×720) |
| **Python** | 3.10+ |
| **Plex Server** | `http://192.168.0.2:32400` (LAN) |

---

## 4. Codebase Structure

```
htpcstation/
  main.py                              # Entry point, PySide6 engine, context properties, font loading,
                                       # keyboard/gamepad detection, window hide/show on process launch
  assets/
    fonts/
      NotoEmoji-Regular.ttf            # Bundled emoji font (879KB, OFL license) — loaded but Qt
                                       # doesn't reliably use it as fallback (see gotchas)
  backend/
    __init__.py
    browser_launcher.py                # Brave kiosk launcher, session cleanup, PID tracking
    config.py                          # JSON config, 20 system defaults, all setters auto-save
    gamepad.py                         # evdev → QKeyEvent injection, auto-repeat, hotplug
    gamelist.py                        # gamelist.xml parser, write_game_stats()
    keys.py                            # Semantic key abstraction + input source tracking (gamepad/keyboard)
    launcher.py                        # QProcess emulator launcher, PID/time tracking
    library.py                         # GameLibrary QObject: models, collections, sort, launch, favorites
    models.py                          # Game and System dataclasses
    plex_client.py                     # Plex Media Server HTTP client (requests)
    plex_library.py                    # PlexLibrary QObject: threaded data loading, models, sort/filter
    plex_models.py                     # PlexMovie, PlexShow, PlexSeason, PlexEpisode dataclasses
    poster_cache.py                    # Thread-safe poster downloader, SHA256 hash filenames
    settings_manager.py                # SettingsManager QObject: wraps Config for QML access
  qml/
    main.qml                           # ApplicationWindow, vpx(), QuitDialog
    Theme.qml                          # Singleton: colors, fonts, animation durations
    qmldir                             # Singleton registration
    components/
      ClockDisplay.qml                 # HH:MM clock, 1s timer
      FocusRing.qml                    # Reusable focus indicator
      QuitDialog.qml                   # Modal quit confirmation
      SettingButton.qml                # Action button row for settings
      SettingSlider.qml                # Numeric slider row for settings
      SettingTextInput.qml             # Text input row for settings (with edit mode)
      SettingToggle.qml                # Boolean toggle row for settings
    screens/
      HomeScreen.qml                   # Tab bar (Games/Watch/Settings), content loader, clock
      GamesScreen.qml                  # System list + game grid + detail view (3-state)
      GameGridView.qml                 # Scrollable game grid with screenshots, sort overlay
      GameDetailView.qml               # Game metadata, video snap playback, launch/favorite
      WatchScreen.qml                  # Plex library list + movie/show grids + detail views
      PlexMovieGrid.qml                # Movie poster grid, infinite scroll, sort/filter overlay
      PlexMovieDetail.qml              # Movie metadata, poster, play action
      PlexShowGrid.qml                 # TV show poster grid, sort/filter overlay
      PlexShowDetail.qml               # Show metadata, horizontal season tabs, episode list
      SettingsScreen.qml               # 4-section settings menu (Games, Plex, Browser, UI)
  tests/
    test_gamelist_parser_fixes.py      # 7 tests
    test_emulator_launch.py            # 15 tests
    test_collections.py                # 20 tests
    test_filter_sort.py                # 12 tests
    test_plex_backend.py               # ~100 tests
    test_browser_launch.py             # ~20 tests
    test_settings_backend.py           # 39 tests
    test_video_snap.py                 # ~10 tests
```

---

## 5. What's Been Built

### M0 — Shell ✅
- Fullscreen PySide6 + QML application
- Home screen with tab navigation: Games, Watch, Settings
- Gamepad input via evdev (D-pad, sticks, face buttons, triggers, bumpers)
- Keyboard fallback (arrow keys, Enter, Escape, F-keys)
- Semantic key abstraction (`keys.isAccept()`, `keys.isCancel()`, etc.)
- Auto-repeat on held buttons (500ms initial, 80ms repeat)
- Visible focus ring on all navigable elements
- Animated screen transitions (slide-in, 250ms)
- 24-hour clock display (top-right)
- Quit dialog (Start button or Escape from tab bar)
- Focus save/restore across dialog open/close
- D-pad Down from tab bar enters content area

### M1 — Games (ROMs) ✅
- Config system: JSON config with ROM directory, RetroArch flatpak command, per-system core mapping, 20 built-in system defaults
- Gamelist parser: parses `gamelist.xml` per system, resolves relative `<image>` and `<video>` paths
- System list view: navigable list of discovered platforms with game counts
- Game grid view: scrollable grid with screenshot artwork, async image loading
- Game detail view: full metadata, video snap playback (MediaPlayer + VideoOutput, 1.5s delay, looping, muted), star rating, scrollable description
- Emulator launch: QProcess-based, `flatpak run org.libretro.RetroArch --fullscreen -L <core> <rom>`
- Play stats write-back: updates `lastplayed`, `playcount`, `gametime`, `favorite` in gamelist.xml
- Favorite toggle: X button, persists to XML, toast notification (2-second auto-dismiss)
- Collections: Favorites, Last Played (50 most recent), All Games — virtual systems at top of list
- Sort: A-Z, Z-A, Recent — Y button opens sort overlay
- Left/Right in game detail navigates to prev/next game

### M2 — Plex ✅
- Plex API client: libraries, movies, shows, seasons, episodes, on-deck, identity
- Data models: PlexMovie, PlexShow, PlexSeason, PlexEpisode with parsing helpers
- Poster cache: thread-safe downloader, SHA256 hash filenames, `***REMOVED***.config/htpcstation/poster_cache/`
- PlexLibrary QObject: threaded data loading (ThreadPoolExecutor), progressive poster loading
- Watch screen: library list with "Plex" header, Continue Watching, Movies, TV Shows, DVR
- Movie grid: poster grid with infinite scroll (50 per page), portrait cells
- Movie detail: poster, metadata (studio, rating, score, runtime, genre, director, cast), tagline, synopsis
- TV show grid: poster grid with episode progress indicators
- TV show detail: show metadata + horizontal season tabs + episode list with watched indicators (●/○/◐)
- Plex sort & filter: server-side sort (A-Z, Z-A, Recently Added, Year, Rating) + genre filter via Y button
- Browser launch: Brave kiosk mode deep-link to Plex Web with `autoPlay=1`
- Window hide/show: HTPC Station hides when browser/emulator launches, restores on exit
- Browser session cleanup: clears `Sessions/` and `Session Storage/` from Brave's default profile before each launch to prevent tab accumulation
- Left/Right in movie detail navigates to prev/next movie
- Poster images display in detail views (cached during `getMovie()`/`getShow()`)

### Settings UI ✅
- SettingsManager QObject wrapping Config with Q_PROPERTYs and Slots
- 4 sections: Games, Plex, Browser, User Interface
- Reusable components: SettingTextInput (with edit mode), SettingToggle, SettingButton, SettingSlider
- Games: ROMs Directory, RetroArch Command, Cores Directory, Rescan Library button
- Plex: Server URL, Token (masked), Test Connection button
- Browser: Browser Command
- User Interface: Video Snap Autoplay toggle, Video Snap Delay slider (0-5000ms, 100ms steps)
- All changes auto-save to config.json
- Per-system core editor: placeholder ("Coming soon")

### Input Source Detection ✅
- `Keys` object tracks `useGamepadLabels` property (bool)
- GamepadManager calls `keys.setGamepadInput()` on every injected key press
- Event filter detects `spontaneous()` keyboard events → `keys.setKeyboardInput()`
- All action hint bars switch between gamepad labels (A/B/X/Y) and keyboard labels (Enter/Esc/F1/F2)
- 7 hint bar locations updated across all detail views, grid headers, and sort overlays

---

## 6. Gamepad Controls

| Button | evdev Code | Qt Key | Action |
|---|---|---|---|
| A (physical) | BTN_EAST | Key_Return | Accept / confirm / launch |
| B (physical) | BTN_SOUTH | Key_Escape | Cancel / back |
| X | BTN_NORTH | Key_F1 | Context action 1 (favorite) |
| Y | BTN_WEST | Key_F2 | Context action 2 (sort) |
| Start | BTN_START | Key_F10 | Quit dialog |
| Select | BTN_SELECT | Key_F9 | Secondary menu |
| LB | BTN_TL | Key_PageUp | Previous tab |
| RB | BTN_TR | Key_PageDown | Next tab |
| LT | ABS_Z | Key_Home | Page scroll up |
| RT | ABS_RZ | Key_End | Page scroll down |
| D-pad / Left stick | — | Key_Up/Down/Left/Right | Navigation |

**Note:** A/B mapping is swapped from evdev convention (`BTN_SOUTH`=A) to match the user's physical controller. This is hardcoded — button remapping UI is deferred to v2+.

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
    "server_url": "http://192.168.0.2:32400",
    "token": "<plex_token>"
  },
  "browser": {
    "command": "flatpak run com.brave.Browser"
  },
  "ui": {
    "video_snap_autoplay": true,
    "video_snap_delay_ms": 1500
  }
}
```

---

## 8. Gotchas & Lessons Learned

### QML Component ID Shadowing
Setting components (`SettingTextInput`, etc.) originally used `id: root` which shadowed the `ApplicationWindow`'s `root` where `vpx()` is defined. This caused `vpx is not a function` errors. **Fix:** Each component uses a unique id (`textInputRoot`, `toggleRoot`, `buttonRoot`, `sliderRoot`). **Rule:** Never use `id: root` in any component — that id belongs to the ApplicationWindow.

### QML Signal Name Conflicts
`signal valueChanged(string newValue)` conflicts with QML's auto-generated `valueChanged` signal from `property string value`. This made the component type "unavailable" and cascaded errors to other screens. **Fix:** Renamed to `signal valueEdited(...)`. **Rule:** Never name a signal `<propertyName>Changed` — QML auto-generates those.

### Brave Flatpak Session Accumulation
Brave saves session state on exit. Each `--kiosk <url>` launch adds a tab. Without cleanup, tabs accumulate. **Fix:** Before each launch, clear `Sessions/` and `Session Storage/` directories from Brave's default profile at `***REMOVED***.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default/`.

### Brave Flatpak `--user-data-dir` Doesn't Work
The flatpak sandbox restricts filesystem access. Custom `--user-data-dir` paths outside the sandbox are silently ignored, causing a fresh profile each launch (losing Plex login). **Fix:** Use Brave's default profile (which the sandbox can access) and only clear session files.

### Brave Focus on Launch
HTPC Station's fullscreen window keeps focus when launching Brave. **Fix:** Hide the HTPC Station window on process launch (`window.hide()`), restore on exit (`window.showFullScreen()`, `window.raise_()`, `window.requestActivate()`).

### Plex User Selection Prompt
Plex Home with multiple users shows a "select user" prompt in Plex Web. The `autoPlay=1` parameter only works after user selection. Brave remembers the session after first selection, so subsequent launches skip the prompt. **Deferred:** Proper fix via Plex user API.

### Gamepad evdev Crash Loop
`InputDevice.read()` returns a generator. The actual `device_read_many` call happens during iteration, not on `.read()`. The `OSError` catch must wrap the entire `for event in events:` loop, not just the `.read()` call.

### VAAPI Decoding Errors
Video snap playback logs harmless VAAPI hardware decoding errors when the iGPU doesn't support the H.264 profile. ffmpeg falls back to software decoding automatically. **Fix:** `os.environ.setdefault("LIBVA_MESSAGING_LEVEL", "0")` in main.py.

### Qt 6 Video Convenience Type
The `Video` QML type didn't render video despite loading the file. **Fix:** Use explicit `MediaPlayer` + `VideoOutput` components instead, with a 100ms+ delay before calling `play()`.

### PlexLibrary Client Not Recreated on Config Change
`PlexLibrary._setup_client()` was only called in `__init__`. If config changed (e.g., via settings UI), the client wasn't recreated. **Fix:** Call `_setup_client()` at the start of `refresh()`.

### WatchScreen Single Refresh
`_refreshed` flag prevented re-refresh after a failed first attempt (e.g., no Plex client configured). **Fix:** Also retry when `_libraryEntries.length === 0`.

### QML Context Property Null on Startup
QML evaluates bindings during component creation before context properties are set. Any binding that reads `plex.*` or `settings.*` will get null on first evaluation. **Fix:** Add null guards (`if (!settings) return ""`) in functions that read context properties eagerly.

### Bundled Emoji Font
NotoEmoji-Regular.ttf is bundled and loaded via `QFontDatabase.addApplicationFont()`, but Qt doesn't reliably use it as a fallback for all emoji glyphs (particularly `🎮`). **Workaround:** Collection display names use plain text (no emoji prefixes). The font file remains bundled for potential future use.

---

## 9. Temporary Decisions

These are intentional shortcuts that should be revisited:

| Decision | Location | Why | Future Fix |
|---|---|---|---|
| Hardcoded ROM path fallback | `main.py` line 33-34 | Sets ROM dir to `***REMOVED***opencode/ROMs` when config is empty | Remove once first-run setup exists |
| A/B button swap | `backend/gamepad.py` lines 48-49 | `BTN_EAST`=Accept, `BTN_SOUTH`=Cancel — matches user's controller | Add button remapping in settings |
| Plex token in config.json | `config.json` | Plaintext token, editable via settings | Implement Plex OAuth flow |
| `waitForStarted(3000)` blocking | `launcher.py`, `browser_launcher.py` | Blocks main thread for up to 3s on process launch | Use async `QProcess.errorOccurred` signal |
| Synchronous `getMovie()`/`getShow()` | `plex_library.py` | Blocks main thread briefly for API call + poster download | Move to threaded worker |
| Synchronous `testPlexConnection()` | `settings_manager.py` | Blocks main thread during connection test | Defer to thread (partially mitigated with `Qt.callLater`) |
| Per-system core editor | `SettingsScreen.qml` | Shows "Coming soon" toast | Build sub-screen with system list and editable cores |
| `--kiosk` + `--start-fullscreen` | `browser_launcher.py` | Both flags used for Brave fullscreen | May only need one; test on other Chromium browsers |

---

## 10. Remaining Milestones

### M3 — Steam
- Parse `***REMOVED***.steam/steam/steamapps/appmanifest_*.acf` for installed games
- Display Steam games alongside ROM platforms in Games section
- Header image artwork from `cdn.cloudflare.steamstatic.com`, cached locally
- Launch via `xdg-open steam://rungameid/<id>`
- Recently played from ACF `LastPlayed` timestamps
- Degrade gracefully when offline (show text-only, no artwork)

### M4 — Moonlight
- Read paired hosts from `***REMOVED***.config/Moonlight Game Streaming/`
- TCP probe on port 47990 for host availability
- `GET https://<host>:47990/api/apps` for app enumeration (self-signed cert)
- Cross-reference app names with Steam Store API for artwork
- Launch: `moonlight stream -app "<app_name>" <host_ip>`
- Multi-host support, "Host Unavailable" graceful state

### M5 — Home Screen
- Unified "Recently Played / Continue Watching" row spanning all content types
- Plex "On Deck" in-progress items
- Recently played ROMs (from gamelist.xml `lastplayed`)
- Recently played Steam games (from ACF `LastPlayed`)
- Recent Moonlight sessions
- "Recently Added" row (new Plex library additions)
- Background fanart cycling from currently highlighted content
- Network/host availability indicators
- Graceful offline state

### M6 — Hardening
- Performance profiling on J5005 reference hardware (60fps, <200MB idle RAM)
- Memory optimization
- Offline graceful degradation
- Autostart documentation (systemd user service vs `.xinitrc`)
- `QProcess` async start (replace `waitForStarted`)
- Path matching robustness in `write_game_stats`
- Guard `_on_process_finished` against stale model references
- Emit `systemsModelChanged` after `_rebuild_collections` so collection game counts update in real-time
- Unit test infrastructure improvements, CI

### Deferred Items (no milestone assigned)
- Detail list view toggle (alternative to grid for games)
- Custom user-defined game collections
- Standalone emulator support (Dolphin, PCSX2)
- Per-system core editor sub-screen in settings
- Plex OAuth authentication (replace hardcoded token)
- Plex user/profile selection via API (bypass "select user" prompt)
- Plex search
- Mark watched/unwatched in Plex
- On Deck content view (browse Continue Watching items)
- Gamepad button remapping in settings
- On-screen keyboard for 10-foot text input

### v2+ (Out of scope for v1)
- WebSocket server for Chrome extension IPC (port 37371)
- Chrome extension — gamepad navigation for browser-based content
- YouTube — `youtube.com/tv` kiosk launch
- Streaming services — Netflix, Hulu, Prime, Max, Disney+, Apple TV+
- TMDB integration for streaming service metadata
- GOG / Epic / other PC game stores
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
- Fedora Linux, flatpak RetroArch, flatpak Brave
- Video snap delay: 1500ms
- Keyboard navigation is a first-class citizen (adaptive hint labels)
- Version control via git from this point forward
- Settings sections: "Games" (not "Library" or "Emulators"), "Plex", "Browser", "User Interface" (not "Display")

---

## 12. Architecture Notes for New Agent

### QML Context Properties
Four Python objects are exposed to QML:
- `keys` — `Keys` instance (semantic key checks + input source tracking)
- `library` — `GameLibrary` instance (ROM data, models, launch, favorites)
- `plex` — `PlexLibrary` instance (Plex data, models, sort/filter, browser launch)
- `settings` — `SettingsManager` instance (config read/write for settings UI)

### Focus Management Pattern
- Every screen/component is a `FocusScope` with `enabled: focus`
- Gamepad events are injected as `QKeyEvent`s — QML only sees keyboard events
- `FocusRing.qml` shows on `parent.activeFocus`
- `vpx()` function lives on the `ApplicationWindow` (id: `root`) — child components must NOT shadow this id

### Threading Model
- All UI on the Qt main thread
- Plex API calls via `ThreadPoolExecutor(max_workers=2)` with results delivered via Qt signals
- Poster downloads happen on thread pool, `dataChanged` emitted on main thread
- Emulator/browser launch via `QProcess` (non-blocking after start)

### Process Lifecycle
- When emulator or browser launches: `processStarted` signal → `window.hide()`
- When process exits: `processFinished` signal → `window.showFullScreen()` + `raise_()` + `requestActivate()`
- Browser session files cleared before each launch to prevent tab accumulation

### Task Brief Archive
All task briefs from the implementation are at:
- `***REMOVED***opencode/misc/coding-team/m0-shell/` (tasks 001–004)
- `***REMOVED***opencode/misc/coding-team/m1-games/` (tasks 005–014)
- `***REMOVED***opencode/misc/coding-team/m2-plex/` (tasks 015–020)
- `***REMOVED***opencode/misc/coding-team/deferred-batch-1/` (tasks 021–024)
- `***REMOVED***opencode/misc/coding-team/settings/` (tasks 025–026)

---

*End of resume document. Start the next session by reading this file and the original proposal at `***REMOVED***opencode/proposal.md`.*
