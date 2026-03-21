# HTPC Station — Project Resume Document

> Hand this file to a fresh agent context to resume development without losing progress.

---

## 1. Project Summary

**HTPC Station** turns any old mini PC or thin client into a living room entertainment hub. It is a single 10-foot gamepad-navigable interface that unifies retro game emulation, PC gaming via Steam, game streaming via Moonlight, and Plex media browsing — all from one home screen.

**Core principle:** HTPC Station owns browsing, metadata, and navigation. Launch backends handle execution — emulators, Steam URI, Moonlight CLI, Plex Web. HTPC Station is a launcher and library browser, not a media player or emulator.

**Original proposal:** `***REMOVED***opencode/proposal.md` (v3.0). Some decisions have been revised during implementation — this document reflects the current state.

---

## 2. Technology Stack

| Component | Choice |
|---|---|
| **Framework** | Qt 6 / QML + PySide6 (Python backend) |
| **Target Platform** | Linux x86_64, Xorg, optimized for Intel J5005 / UHD 605 |
| **Emulator** | RetroArch via Flatpak (`flatpak run org.libretro.RetroArch --fullscreen -L <core> <rom>`) |
| **Gamepad Input** | `evdev` → synthetic `QKeyEvent` injection (Pegasus Frontend pattern) |
| **Config** | JSON at `***REMOVED***.config/htpcstation/config.json` |
| **Resolution** | 1920×1080 fullscreen, `vpx()` scaling function (base 1280×720) |
| **Python** | 3.10+ |
| **Dependencies** | PySide6, evdev |

**Key architectural decisions made:**
- **Build from scratch** (not forking Pegasus Frontend — Pegasus is Qt5/C++ and too tightly coupled to ROM/game concepts)
- **No WebSocket server** in v1 (dropped entirely — trivial to add later for Chrome extension IPC)
- **One hardcoded visual style** — but `Theme.qml` singleton centralizes all colors/fonts/spacing for future theming
- **Gamepad button mapping:** `BTN_EAST` = A (Accept), `BTN_SOUTH` = B (Cancel) — matches the user's physical controller layout (reversed from evdev convention)

---

## 3. Codebase Structure

All code is at `***REMOVED***opencode/htpcstation/`:

```
htpcstation/
  main.py                              # Entry point, PySide6 engine, context properties, font loading
  assets/
    fonts/
      NotoEmoji-Regular.ttf            # Bundled emoji font (879KB, OFL license)
  backend/
    __init__.py
    config.py                          # JSON config, system defaults (~20 systems), launch command builder
    gamepad.py                         # evdev gamepad → QKeyEvent injection, auto-repeat, hotplug
    gamelist.py                        # gamelist.xml parser, write_game_stats()
    keys.py                            # Semantic key abstraction (keys.isAccept(), etc.)
    launcher.py                        # QProcess-based emulator launcher, PID/time tracking
    library.py                         # GameLibrary QObject: models, collections, sort, launch, favorites
    models.py                          # Game and System dataclasses
  qml/
    main.qml                           # ApplicationWindow, vpx(), QuitDialog
    Theme.qml                          # Singleton: colors, fonts, animation durations
    qmldir                             # Singleton registration
    components/
      FocusRing.qml                    # Reusable focus indicator
      ClockDisplay.qml                 # HH:MM clock, 1s timer
      QuitDialog.qml                   # Modal quit confirmation
    screens/
      HomeScreen.qml                   # Tab bar (Games/Watch/Settings), content loader, clock
      GamesScreen.qml                  # System list + game grid + detail view (3-state)
      GameGridView.qml                 # Scrollable game grid with screenshots
      GameDetailView.qml               # Full metadata, launch/favorite actions, toast notification
      WatchScreen.qml                  # Placeholder
      SettingsScreen.qml               # Placeholder
  tests/
    test_gamelist_parser_fixes.py      # 7 tests
    test_emulator_launch.py            # 15 tests
    test_collections.py                # 20 tests
    test_filter_sort.py                # 12 tests
```

**54 tests total, all passing.**

**Reference data:** `***REMOVED***opencode/ROMs/` — three systems (gb, ngpc, sega32x) with gamelist.xml, screenshots, and videos per system.

**Reference repos** (read-only, for pattern reference): `***REMOVED***opencode/es-de/`, `***REMOVED***opencode/pegasus-frontend/`

---

## 4. What's Been Built (M0 + M1)

### M0 — Shell (Complete)
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

### M1 — Games (Complete)
- **Config system:** JSON config with ROM directory, RetroArch flatpak command, per-system core mapping, 20 built-in system defaults
- **Gamelist parser:** Parses `gamelist.xml` per system, resolves relative `<image>` and `<video>` paths, handles malformed XML gracefully
- **QML models:** `SystemListModel` and `GameListModel` (QAbstractListModel) exposed via `GameLibrary` context property
- **System list view:** Navigable list of discovered platforms with game counts
- **Game grid view:** Scrollable grid with screenshot artwork, async image loading, placeholder for missing images
- **Game detail view:** Full metadata (screenshot, developer, publisher, genre, players, release year, star rating), scrollable description, action hints bar
- **Emulator launch:** QProcess-based, `flatpak run org.libretro.RetroArch --fullscreen -L <core> <rom>`, elapsed time tracking
- **Play stats write-back:** Updates `lastplayed`, `playcount`, `gametime`, `favorite` in gamelist.xml after each session
- **Favorite toggle:** X button toggles favorite, persists to XML, toast notification ("Added to Favorites" / "Removed from Favorites", 2-second auto-dismiss)
- **Collections:** Favorites, Last Played (50 most recent), All Games — virtual systems at top of list, rebuilt on access
- **Sort:** A-Z, Z-A, Recent (by last played) — Y button opens sort overlay

### Bugfixes Applied
- Gamepad crash loop on disconnect (OSError during generator iteration)
- RetroArch launches in fullscreen
- A/B button swap to match physical controller layout
- Removed genre filter and genre/players sort options per user preference
- Collection display names use plain text (no emoji prefixes — rendering issues)

---

## 5. How to Run

```bash
cd ***REMOVED***opencode/htpcstation
python3 main.py
```

**Dependencies:** `pip install PySide6 evdev`

**RetroArch:** Installed as flatpak (`org.libretro.RetroArch`). Cores at `***REMOVED***.var/app/org.libretro.RetroArch/config/retroarch/cores/`.

**Installed cores:** `gambatte_libretro.so` (GB), `mednafen_ngp_libretro.so` (NGPC), `gpsp_libretro.so` (GBA), `race_libretro.so` (NGP alt). No 32X core installed yet.

**Tests:** `python3 -m pytest tests/ -q` from the htpcstation directory.

**Config:** First run creates `***REMOVED***.config/htpcstation/config.json`. Currently hardcoded to use `***REMOVED***opencode/ROMs` as the ROM directory (temporary — see `main.py` line 23-24).

---

## 6. Gamepad Controls

| Button | Action |
|---|---|
| D-pad / Left stick | Directional navigation |
| A (BTN_EAST) | Accept / confirm / launch |
| B (BTN_SOUTH) | Cancel / back |
| X (BTN_NORTH) | Context action 1 (favorite toggle) |
| Y (BTN_WEST) | Context action 2 (sort overlay) |
| Start (BTN_START) | Quit dialog |
| LB / RB | Tab switching (Games/Watch/Settings) |
| LT / RT | Page scroll |

**Note:** A/B mapping is swapped from evdev convention to match the user's physical controller. When button remapping is added (v2+), this becomes user-configurable.

---

## 7. Remaining Milestones

### M1.5 — Steam & Polish
Items originally scoped for M1 but deferred:

- **Steam integration** — Parse `***REMOVED***.steam/steam/steamapps/appmanifest_*.acf` for installed games, display alongside ROM platforms in Games section, launch via `xdg-open steam://rungameid/<id>`
- **Steam artwork** — Fetch header images from `cdn.cloudflare.steamstatic.com`, cache locally, degrade gracefully offline (show text-only when no network)
- **Video snap playback** — Play `<video>` paths in game detail view (requires QtMultimedia)
- **Detail list view toggle** — Alternative to grid view, switchable per user preference
- **Custom user-defined collections** — UI for creating/editing collections beyond Favorites/Last Played/All Games
- **Standalone emulator support** — Dolphin, PCSX2, etc. as alternatives to RetroArch cores (per-system configurable)
- **Settings UI** — GUI for editing ROM paths, emulator commands, system config (currently manual JSON editing at `***REMOVED***.config/htpcstation/config.json`)

### M2 — Moonlight (LAN only)
- Read paired hosts from `***REMOVED***.config/Moonlight Game Streaming/`
- TCP probe on port 47990 for host availability
- `GET https://<host>:47990/api/apps` for app enumeration (self-signed cert, disable verification)
- Cross-reference app names with Steam Store API for artwork
- Launch: `moonlight stream -app "<app_name>" <host_ip>`
- Frontend resumes when moonlight process exits
- Multi-host support
- "Host Unavailable" graceful state

### M3 — Plex (LAN / relay)
- Plex.tv OAuth flow, store token in `***REMOVED***.config/htpcstation/plex_token`
- Library browse: Movies, TV Shows (from `GET /library/sections`)
- Full metadata: poster, backdrop, synopsis, year, rating, genre, cast, runtime, seasons/episodes
- Continue Watching with resume position (from `GET /hubs/home`)
- Search across Plex library
- Mark watched/unwatched
- Launch: `chromium --kiosk "http://<server>:32400/web/index.html#!/server/<machineId>/details?key=/library/metadata/<id>"`
- Monitor Chrome PID, resume frontend on exit
- **v1 limitation:** Returning from Plex requires Alt+F4 (Chrome extension in v2 will handle this)

### M4 — Home Screen (Mixed network)
- Unified "Recently Played / Continue Watching" row spanning all content types
- Plex "On Deck" in-progress items
- Recently played ROMs (from gamelist.xml `lastplayed`)
- Recently played Steam games (from ACF `LastPlayed`)
- Recent Moonlight sessions
- "Recently Added" row (new Plex library additions)
- Background fanart cycling from currently highlighted content
- Network/host availability indicators (Plex server, Moonlight host)
- Graceful offline state — rows requiring network show cached data or collapse

### M5 — Hardening (Mixed network)
Per original proposal, plus issues identified during M0/M1:

- Performance profiling on J5005 reference hardware (60fps target, <200MB idle RAM)
- Memory optimization
- Offline graceful degradation
- Autostart documentation (systemd user service vs `.xinitrc`)
- **QProcess async start** — Replace `waitForStarted(3000)` with async error handling via `QProcess.errorOccurred` (flatpak cold starts can exceed 3s)
- **Path matching robustness** — Normalize paths in `write_game_stats` to handle `./` prefix variations
- **System switch during emulator run** — Guard `_on_process_finished` against stale model references
- **SystemListModel stale data** — Emit `systemsModelChanged` after `_rebuild_collections` so collection game counts update in real-time
- **Unit test infrastructure** — Formalize test harness, add CI, increase coverage for gamepad input and QML integration

### v2+ (Out of scope for v1)
Architecture should not block these:

- **WebSocket server** — For Chrome extension IPC (port 37371)
- **Chrome extension** — Gamepad navigation layer for browser-based content
- **YouTube** — `youtube.com/tv` kiosk launch via extension
- **Streaming services** — Netflix, Hulu, Prime, Max, Disney+, Apple TV+ via Chrome kiosk + TMDB metadata
- **TMDB integration** — Movie/TV metadata for streaming services
- **GOG / Epic / other stores** — Additional PC game sources
- **Wayland support** — Currently Xorg only
- **Pluggable theme system** — v1 ships one hardcoded visual style; `Theme.qml` singleton designed for future theming
- **Button remapping** — Gamepad button layout customization in settings
- **Multi-user profiles / parental controls**
- **4K HDR support** — 1080p is the primary target
- **Screensaver**

---

## 8. Resolved Design Decisions

These were open questions in the original proposal. All resolved:

| Question | Decision |
|---|---|
| Fork vs. build | **Build from scratch** — Pegasus is Qt5/C++, too coupled to ROM concepts |
| C++ vs. PySide6 | **PySide6** — cleaner for I/O-bound work, API calls, subprocess management |
| Plex exit mechanism | **Document keyboard shortcut** (Alt+F4) — no overlay window in v1 |
| Theme scope | **One hardcoded style**, but `Theme.qml` singleton centralizes values for future theming |
| WebSocket server | **Dropped from v1** — trivial to add later |
| Emulator backend | **RetroArch flatpak only** for now — standalone emulators deferred to M1.5 |
| Gamepad library | **evdev** (Linux-native, no SDL dependency) |
| Steam in M1 | **Deferred to M1.5** — M1 is ROMs only |
| Video snaps | **Deferred** — show static screenshot only |
| Custom collections | **Deferred** — automatic collections only (Favorites, Last Played, All Games) |

---

## 9. Known Issues / Technical Debt

- **Hardcoded ROM path** — `main.py` line 23-24 sets ROM directory to `***REMOVED***opencode/ROMs` when config is empty. Needs proper first-run setup or settings UI.
- **Button mapping hardcoded** — A/B are swapped from evdev convention for this specific controller. Needs remapping UI.
- **LSP type warnings** — `QAbstractListModel` override signatures don't match PySide6 stubs exactly (works at runtime, pyright complains). Cosmetic.
- **No CI** — Tests run locally only.
- **Font fallback** — Bundled NotoEmoji font loaded but Qt doesn't reliably use it as fallback for all emoji. Collection names use plain text as workaround.

---

## 10. Task Brief Archive

All task briefs are preserved at:
- `***REMOVED***opencode/misc/coding-team/m0-shell/` (tasks 001–004 + fixes)
- `***REMOVED***opencode/misc/coding-team/m1-games/` (tasks 005–014 + fixes)

These document the rationale and constraints for each implementation decision.

---

## 11. User Preferences (Observed)

- Prefers simple, functional UI over polish
- Wants sort options: A-Z, Z-A, Recent only (no genre sort, no genre filter, no players sort)
- Wants confirmation feedback for actions (favorite toggle toast)
- RetroArch should launch fullscreen
- No emoji/symbol prefixes on collection names (rendering issues)
- JSON config preferred over TOML for manual editing
- Fedora Linux, flatpak RetroArch

---

*End of resume document. Start the next session by reading this file and the original proposal at `***REMOVED***opencode/proposal.md`.*
