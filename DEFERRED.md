# HTPC Station — Deferred Items

Items explicitly deferred during M0 and M1 implementation. Organized by when they should be addressed.

---

## Next Milestone: M1.5 — Steam & Polish

These were originally part of M1 but deferred to keep scope manageable.

- **Steam integration** — Parse ACF manifests, display installed Steam games alongside ROM platforms in the Games section, URI launch via `steam://rungameid/<id>`
- **Steam artwork** — Fetch header images from Steam CDN, cache locally, degrade gracefully offline
- **Video snap playback** — Play video snaps in game detail view (requires QtMultimedia dependency)
- **Detail list view toggle** — Alternative to grid view; switchable per user preference
- **Custom user-defined collections** — UI for creating/editing game collections beyond the automatic ones
- **Standalone emulator support** — Dolphin, PCSX2, etc. as alternatives to RetroArch cores
- **Settings UI** — GUI for editing ROM paths, emulator commands, system config (currently manual JSON editing)

## M2 — Moonlight

Per original proposal. No items deferred from M2 yet.

- Sunshine REST API host enumeration
- Host availability check
- `moonlight` CLI launch
- Multi-host support

## M3 — Steam

Deferred from M1.

- Parse ACF manifests for installed games
- Display Steam games alongside ROM platforms in Games section
- Steam artwork fetching from CDN, cached locally
- URI launch via `steam://rungameid/<id>`

## Plex Improvements (deferred from M2)

- **Plex user/profile selection** — Bypass the "select user" prompt on Plex Home by switching to a specific managed user via API (`/api/v2/users/signin`) and using a user-specific token. Currently the user must pick their profile once per browser session (Brave remembers it after first selection).
- **Plex OAuth authentication** — Replace hardcoded token with OAuth flow
- **Plex search** — Search across Plex library
- **Mark watched/unwatched** — Toggle watch status from the UI
- **On Deck content view** — Browse Continue Watching items (currently shows in library list but content view is a placeholder)

## M4 — Home Screen

Per original proposal.

- Unified "Recently Played / Continue Watching" row across all sources
- Fanart background cycling
- Recently Added row
- Network/host availability indicators

## M5 — Hardening

Per original proposal, plus items identified during M0/M1 implementation.

- Performance profiling on J5005 reference hardware
- Memory optimization (idle < 200MB target)
- Offline graceful degradation
- Autostart documentation
- **QProcess async start** — Replace `waitForStarted(3000)` with async error handling via `QProcess.errorOccurred` (flatpak cold starts can exceed 3s)
- **Path matching robustness** — Normalize paths in `write_game_stats` to handle `./` prefix variations
- **System switch during emulator run** — Guard `_on_process_finished` against stale model references if user switches systems while emulator is running
- **SystemListModel stale data** — Emit `systemsModelChanged` after `_rebuild_collections` so collection game counts update in the system list UI in real-time
- **Unit test infrastructure** — Formalize test harness, add CI, increase coverage for gamepad input and QML integration
- **Sort/filter overlay scrollable genre list** — Genre list clips if there are many genres; add scrolling

## v2+ (Per Original Proposal)

Explicitly out of scope for v1. Architecture should not block these.

- **WebSocket server** — Dropped from v1 entirely; trivial to add later
- **Chrome extension** — Gamepad navigation layer for browser-based content
- **YouTube** — `youtube.com/tv` kiosk launch via extension
- **Streaming services** — Netflix, Hulu, Prime, Max, Disney+, Apple TV+ via Chrome kiosk + TMDB metadata
- **TMDB integration** — Movie/TV metadata for streaming services
- **GOG / Epic / other stores** — Additional PC game sources
- **Wayland support** — Currently Xorg only
- **Pluggable theme system** — v1 ships one hardcoded visual style; Theme.qml singleton is designed for future theming
- **Button remapping** — Gamepad button layout customization in settings
- **Multi-user profiles / parental controls**
- **4K HDR support** — 1080p is the primary target
- **Screensaver**
