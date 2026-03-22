# HTPC Station — Project Resume Document (Checkpoint 3)

> Hand this file to a fresh agent context to resume development without losing progress.
> Previous checkpoints: Checkpoint 1 (M0+M1), Checkpoint 2 (through Settings UI). This checkpoint covers all work through Plex server discovery, browser gamepad extension, and M6 hardening pull-forward.

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
- **Tests:** 307 passing (`python3 -m pytest tests/ -q`)
- **Run:** `cd ***REMOVED***opencode/htpcstation && python3 main.py`
- **Dependencies:** `pip install PySide6 evdev requests`

**Reference data:**
- ROMs: `***REMOVED***opencode/ROMs/` (3 systems: gb, ngpc, sega32x with gamelist.xml, screenshots, videos)
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
| **Gamepad Input** | `evdev` → synthetic `QKeyEvent` injection (Pegasus Frontend pattern) |
| **Browser** | Brave via Flatpak, dedicated `--user-data-dir` inside flatpak sandbox |
| **Browser Extension** | Manifest V3 Chromium extension for gamepad control in Plex Web |
| **Config** | JSON at `***REMOVED***.config/htpcstation/config.json` |
| **Resolution** | 1920×1080 fullscreen, `vpx()` scaling function (base 1280×720) |
| **Python** | 3.10+ |
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
    gamepad.py                         # evdev → QKeyEvent injection, auto-repeat, hotplug
    gamelist.py                        # gamelist.xml parser, write_game_stats()
    keys.py                            # Semantic key abstraction + input source tracking (gamepad/keyboard)
    launcher.py                        # QProcess emulator launcher, async signal-based start
    library.py                         # GameLibrary QObject: models, collections, sort, launch, favorites
    models.py                          # Game and System dataclasses
    plex_account.py                    # plex.tv API client: server discovery, home users, user switching
    plex_client.py                     # Plex Media Server HTTP client (requests)
    plex_library.py                    # PlexLibrary QObject: threaded data loading, models, sort/filter,
                                       # server discovery, user switching, browser launch
    plex_models.py                     # PlexMovie, PlexShow, PlexSeason, PlexEpisode dataclasses
    poster_cache.py                    # Thread-safe poster downloader, SHA256 hash filenames
    settings_manager.py                # SettingsManager QObject: wraps Config for QML access
  extension/                           # Chromium browser extension (Manifest V3)
    manifest.json                      # Extension manifest, content scripts on all URLs
    content.js                         # Gamepad API polling loop, edge detection, auto-repeat, A/B swap
    mappings/
      default.js                       # No-op fallback mapping for non-Plex sites
      index.js                         # Site matcher: selects mapping based on URL path
      plex.js                          # Plex Web mapping: player controls, virtual focus cursor,
                                       # auto-user-select, auto-play
  qml/
    main.qml                           # ApplicationWindow, vpx(), QuitDialog
    Theme.qml                          # Singleton: colors, fonts, animation durations
    qmldir                             # Singleton registration
    components/
      ClockDisplay.qml                 # HH:MM clock, 1s timer
      FocusRing.qml                    # Reusable focus indicator
      QuitDialog.qml                   # Modal quit confirmation
      SettingButton.qml                # Action button row for settings
      SettingSelect.qml                # Cycle-through selector row for settings (server/user picker)
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
    test_emulator_launch.py            # ~25 tests
    test_collections.py                # ~24 tests
    test_filter_sort.py                # 12 tests
    test_plex_backend.py               # ~150 tests
    test_plex_account.py               # ~28 tests
    test_browser_launch.py             # ~40 tests
    test_settings_backend.py           # ~40 tests
    test_video_snap.py                 # ~5 tests
```

---

## 5. What's Been Built

### M0 — Shell ✅
- Fullscreen PySide6 + QML application
- Home screen with tab navigation: Games, Watch, Settings
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

### M1 — Games (ROMs) ✅
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
- **Server discovery:** Automatic via plex.tv resources API (`PlexAccount.get_resources()`). User provides only their plex.tv token. Connection URL selection prefers local direct IP > plex.direct > relay.
- **User switching:** Home users listed via plex.tv API (`PlexAccount.get_home_users()`). Selected user's token obtained via `switch_user()`. Admin token used for server API calls (managed users lack direct server access); user-specific token used for browser deep links only.
- **PlexAccount client** (`backend/plex_account.py`): plex.tv API for server discovery, home user listing, user switching, token validation. Old `/api/` endpoints use XML responses and token-as-query-parameter.
- Plex API client: libraries, movies, shows, seasons, episodes, on-deck, identity
- Data models: PlexMovie, PlexShow, PlexSeason, PlexEpisode with parsing helpers
- Poster cache: thread-safe downloader, SHA256 hash filenames, `***REMOVED***.config/htpcstation/poster_cache/`
- PlexLibrary QObject: threaded data loading (ThreadPoolExecutor), progressive poster loading, server discovery, user switching, lazy reconnect
- Watch screen: library list with "Plex" header, Continue Watching, Movies, TV Shows, DVR
- Movie grid: poster grid with infinite scroll (50 per page), portrait cells
- Movie detail: poster, metadata (studio, rating, score, runtime, genre, director, cast), tagline, synopsis
- TV show grid: poster grid with episode progress indicators
- TV show detail: show metadata + horizontal season tabs + episode list with watched indicators (●/○/◐)
- Plex sort & filter: server-side sort (A-Z, Z-A, Recently Added, Year, Rating) + genre filter via Y button
- **Browser launch:** Deep-link to `app.plex.tv` with user token. Auto-user-select and auto-play via browser extension. Dedicated Brave instance with isolated `--user-data-dir`.
- Window hide/show: HTPC Station hides when browser/emulator launches, restores on exit
- Left/Right in movie detail navigates to prev/next movie
- Poster images display in detail views (cached during `getMovie()`/`getShow()`)

### Browser Gamepad Extension ✅
- **Manifest V3 Chromium extension** at `htpcstation/extension/`
- **Gamepad API polling:** `requestAnimationFrame` loop, edge detection for button presses, auto-repeat (400ms initial, 100ms repeat) for D-pad only
- **A/B swap:** Button 0 → cancel, button 1 → accept (matches physical controller layout)
- **Analog stick deadzone:** ±0.3, converted to digital directional events
- **Site-aware mapping system:** hostname/path-based dispatch, extensible to future sites
- **Plex Web mapping:**
  - Player mode: A=play/pause, B=close player, D-pad=seek/volume, Y=fullscreen, Start=exit
  - Navigation mode: virtual focus cursor with spatial navigation, A=click, B=escape, Start=exit
- **Auto-user-select:** Reads `htpc_user` from URL, polls for `.user-select-modal`, clicks matching user tile, re-navigates to original deep link after 1.5s
- **Auto-play:** Polls for `[data-testid="preplay-play"]` button, clicks it. Triggers on both page load and `hashchange` events (SPA navigation).
- **Extension deployment:** Copied to `***REMOVED***.var/app/com.brave.Browser/config/htpcstation-extension/` before each launch (flatpak sandbox access)

### Settings UI ✅
- SettingsManager QObject wrapping Config with Q_PROPERTYs and Slots
- 4 sections: Games, Plex, Browser, User Interface
- Reusable components: SettingTextInput (with edit mode), SettingToggle, SettingButton, SettingSlider, SettingSelect (cycle-through picker)
- Games: ROMs Directory, RetroArch Command, Cores Directory, Rescan Library button
- Plex: Token (masked), Test Connection button, Server selector (cycle through discovered servers), User selector (cycle through home users)
- Browser: Browser Command
- User Interface: Video Snap Autoplay toggle, Video Snap Delay slider (0-5000ms, 100ms steps)
- All changes auto-save to config.json
- Per-system core editor: placeholder ("Coming soon")
- Server/user selection uses `optionsProvider` function (fetches fresh data on each A press, not a static binding)
- `selectServer`/`selectUser` save config and invalidate client without blocking (lazy reconnect on next `refresh()`)

### Input Source Detection ✅
- `Keys` object tracks `useGamepadLabels` property (bool)
- GamepadManager calls `keys.setGamepadInput()` on every injected key press
- Event filter detects `spontaneous()` keyboard events → `keys.setKeyboardInput()`
- All action hint bars switch between gamepad labels (A/B/X/Y) and keyboard labels (Enter/Esc/F1/F2)
- 7 hint bar locations updated across all detail views, grid headers, and sort overlays

### M6 — Hardening (partial) ✅
- **Async QProcess start:** Replaced blocking `waitForStarted(3000)` with signal-based flow (`QProcess.started` + `QProcess.errorOccurred`) in both `Launcher` and `BrowserLauncher`
- **Stale model guard:** `_on_process_finished` compares stored model reference to current model; skips QML notification if user navigated away during gameplay
- **Collection game counts:** `_rebuild_collections()` rebuilds `SystemListModel` and emits `systemsModelChanged` so Favorites/Last Played counts update immediately
- **Test config isolation:** Fixed `TestSettingsManagerSetters._make_manager()` writing to real `***REMOVED***.config/htpcstation/config.json` (was wiping Plex credentials on every test run)

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
| D-pad | — | Key_Up/Down/Left/Right | Navigation |

**Note:** A/B mapping is swapped from evdev convention (`BTN_SOUTH`=A) to match the user's physical controller. The same swap is applied in the browser extension (Web Gamepad API button 0 → cancel, button 1 → accept). This is hardcoded — button remapping UI is deferred to v2+.

**Note:** The user's controller does not have analog sticks. Stick support exists in the extension (deadzone ±0.3, digital conversion) but is untested.

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
  "ui": {
    "video_snap_autoplay": true,
    "video_snap_delay_ms": 1500
  }
}
```

**Config changes from Checkpoint 2:**
- `plex.server_url` removed — server URL is now resolved at runtime via plex.tv resources API
- `plex.server_id` added — machine identifier of the selected Plex server (persisted)
- `plex.user_id` added — integer ID of the selected Plex Home user (persisted, 0 = admin/default)
- Old config files with `server_url` are handled gracefully (ignored, no crash)

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

### Brave Flatpak Session Accumulation
Brave saves session state on exit. Each `--kiosk <url>` launch adds a tab. Without cleanup, tabs accumulate. **Fix:** Before each launch, clear `Sessions/` and `Session Storage/` directories from the browser profile.

### Brave Flatpak `--user-data-dir` — Revised
The flatpak sandbox restricts filesystem access. Custom `--user-data-dir` paths **outside** the sandbox are silently ignored. **Fix (revised):** Use a dedicated `--user-data-dir` **inside** the flatpak sandbox at `***REMOVED***.var/app/com.brave.Browser/config/htpcstation-browser/`. This creates a completely separate Brave instance that doesn't conflict with personal browsing, ensures kiosk mode and extensions always load (even if Brave is already running), and preserves Plex login across launches.

### Brave Existing Instance Ignores Command-Line Flags
If Brave is already running (personal browsing), launching a new URL joins the existing process. `--kiosk`, `--start-fullscreen`, and `--load-extension` flags are silently ignored. The URL opens as a new tab in the existing window. **Fix:** The dedicated `--user-data-dir` creates a separate Brave process, so flags always apply.

### Brave Focus on Launch
HTPC Station's fullscreen window keeps focus when launching Brave. **Fix:** Hide the HTPC Station window on process launch (`window.hide()`), restore on exit (`window.showFullScreen()`, `window.raise_()`, `window.requestActivate()`).

### Plex User Selection Screen Cannot Be Bypassed via URL
Plex Web always shows the user selection screen for multi-user Plex Home accounts. Passing `X-Plex-Token` in the URL (query string or hash fragment) does not bypass it. The "automatically sign in" feature mentioned in Plex docs is a native app setting, not available in Plex Web. **Fix:** Browser extension auto-clicks the correct user tile by matching the `htpc_user` URL parameter against `.username` text in the `.user-select-modal` DOM.

### Plex Web Loses Deep Link After User Selection
After clicking a user in the Plex Web user selection modal, the app navigates to the home screen and loses the original deep link URL (hash fragment). **Fix:** Extension saves the original URL before clicking the user, waits 1.5s for the transition, then re-navigates via `window.location.href`.

### Plex Web Auto-Play Requires hashchange Listener
The content script runs once at `document_idle`. When the auto-user-select re-navigates, Plex Web handles it as a client-side hash change — the page doesn't reload, so the content script doesn't re-execute. **Fix:** `tryAutoPlay()` listens for `hashchange` events in addition to running on initial page load.

### Plex Old API Endpoints Require Token as Query Parameter
The plex.tv `/api/home/users` and `/api/home/users/{id}/switch` endpoints (no `v2`) reject the `X-Plex-Token` header. The token must be passed as a query parameter (`?X-Plex-Token=...`). These endpoints also return XML, not JSON, regardless of the `Accept` header. **Fix:** `PlexAccount` uses `params={"X-Plex-Token": self._token}` for old endpoints and parses responses with `xml.etree.ElementTree`.

### Plex Managed Users Cannot Access Server Directly
Managed/restricted Plex Home users (e.g., "Kids") get a user-specific token from `switch_user()`, but this token returns 401 when used against the media server API. **Fix:** Always use the admin token for server API calls (library browsing, metadata, posters). The user-specific token is only used in browser deep links so Plex Web applies the correct user profile and content restrictions at playback time. **Consequence:** HTPC Station's library view shows the full catalog regardless of selected user; content restrictions are enforced only in Plex Web during playback.

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
QML evaluates bindings during component creation before context properties are set. Any binding that reads `plex.*` or `settings.*` will get null on first evaluation. **Fix:** Add null guards (`if (!settings) return ""`) in functions that read context properties eagerly.

### Bundled Emoji Font
NotoEmoji-Regular.ttf is bundled and loaded via `QFontDatabase.addApplicationFont()`, but Qt doesn't reliably use it as a fallback for all emoji glyphs (particularly `🎮`). **Workaround:** Collection display names use plain text (no emoji prefixes). The font file remains bundled for potential future use.

---

## 9. Temporary Decisions

These are intentional shortcuts that should be revisited:

| Decision | Location | Why | Future Fix |
|---|---|---|---|
| A/B button swap | `backend/gamepad.py` lines 48-49, `extension/content.js` | `BTN_EAST`=Accept, `BTN_SOUTH`=Cancel — matches user's controller | Add button remapping in settings |
| Plex token in config.json | `config.json` | Plaintext token, editable via settings | Implement Plex OAuth flow |
| Synchronous `getMovie()`/`getShow()` | `plex_library.py` | Blocks main thread briefly for API call + poster download | Move to threaded worker |
| Synchronous `testPlexConnection()` | `settings_manager.py` | Blocks main thread during connection test | Defer to thread (partially mitigated with `Qt.callLater`) |
| Per-system core editor | `SettingsScreen.qml` | Shows "Coming soon" toast | Build sub-screen with system list and editable cores |
| `--kiosk` + `--start-fullscreen` | `browser_launcher.py` | Both flags used for Brave fullscreen | May only need one; test on other Chromium browsers |
| Full catalog for managed users | `plex_library.py` | Admin token used for API (managed user token gets 401) | Filter catalog client-side using user's restriction profile |
| Auto-user-select 1.5s delay | `extension/mappings/plex.js` | Fixed delay before re-navigating after user selection | Detect navigation completion instead of fixed timeout |

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

### M6 — Hardening (remaining items)
- Performance profiling on J5005 reference hardware (60fps, <200MB idle RAM)
- Memory optimization
- Offline graceful degradation
- Autostart documentation (systemd user service vs `.xinitrc`)
- Path matching robustness in `write_game_stats`
- Unit test infrastructure improvements, CI

### Deferred Items (no milestone assigned)
- Detail list view toggle (alternative to grid for games)
- Custom user-defined game collections
- Standalone emulator support (Dolphin, PCSX2)
- Per-system core editor sub-screen in settings
- Plex OAuth authentication (replace plaintext token)
- Plex search
- Mark watched/unwatched in Plex
- On Deck content view (browse Continue Watching items)
- Gamepad button remapping in settings
- On-screen keyboard for 10-foot text input
- Filter Plex catalog for managed users (client-side restriction profile)
- Gamepad extension: YouTube, Netflix, and other site mappings

### v2+ (Out of scope for v1)
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
- Prefers Chromium/Brave for Plex playback over native players (hardware decoding quality)
- Controller does not have analog sticks
- Has multiple Plex servers (owns one, accesses friends' servers)
- Uses Plex Home with multiple users (admin + managed "Kids" profile)

---

## 12. Architecture Notes for New Agent

### QML Context Properties
Four Python objects are exposed to QML:
- `keys` — `Keys` instance (semantic key checks + input source tracking)
- `library` — `GameLibrary` instance (ROM data, models, launch, favorites)
- `plex` — `PlexLibrary` instance (Plex data, models, sort/filter, browser launch, server/user management)
- `settings` — `SettingsManager` instance (config read/write for settings UI)

### Plex Architecture
Two separate API layers:
- **`PlexAccount`** (`plex_account.py`) — talks to `plex.tv` for server discovery, home user listing, user switching. Uses `/api/v2/` (JSON) for resources/user validation and `/api/` (XML) for home users/switching. Token passed as query parameter for old endpoints.
- **`PlexClient`** (`plex_client.py`) — talks to the media server (resolved URL from resources API) for library data, metadata, posters. Always uses the admin token.
- **`PlexLibrary`** (`plex_library.py`) — QObject that orchestrates both. Creates `PlexAccount` from config token, resolves server URL, switches user, creates `PlexClient`. Exposes QML slots for server/user selection. Stores `_active_token` (user-specific) for browser deep links separately from the admin token used by `PlexClient`.

### Browser Extension Architecture
- Content scripts injected on all URLs (Manifest V3, `run_at: document_idle`)
- No ES modules — files concatenated in execution order via manifest `js` array
- Global namespace pattern: `window.__htpcGamepadMappings` for mapping registration
- Site detection: `index.js` checks `window.location.pathname` for `/web/` or `/desktop/`
- Gamepad polling: `requestAnimationFrame` loop in `content.js`, edge detection, auto-repeat for D-pad only
- Extension deployed to `***REMOVED***.var/app/com.brave.Browser/config/htpcstation-extension/` via `shutil.copytree` before each launch

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
- Poster downloads happen on thread pool, `dataChanged` emitted on main thread
- Emulator/browser launch via `QProcess` (async signal-based, non-blocking)

### Process Lifecycle
- When emulator or browser launches: `processStarted` signal → `window.hide()`
- When process exits: `processFinished` signal → `window.showFullScreen()` + `raise_()` + `requestActivate()`
- Browser session files cleared before each launch to prevent tab accumulation
- `launchGame()` sets `_active_game` optimistically; clears on `FailedToStart`

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

---

*End of resume document. Start the next session by reading this file and the original proposal at `***REMOVED***opencode/proposal.md`.*
