# HTPC Station — Changelog

One entry per checkpoint. Task briefs live under `~/opencode/misc/coding-team/`.

---

## CP36 — UI Redesign + Plex cache/offline fixes + offline cache overhaul

Task briefs: `misc/coding-team/ui-redesign/` (006–009), `misc/coding-team/fix-context-button-keycodes/` (004–005, 010–012), `misc/coding-team/plex-offline-cache/` (001–003)

- Theme foundation: neutral palette (#111111/#1c1c1c/#2a2a2a), Liberation Sans, runtime accent/focus ring colors, rounder focus rings (radius 10)
- Focus scale animation (1.05×, 120ms OutCubic) on all focusable delegates across 22 QML files
- ListView/GridView highlight centering (ApplyRange 35%–65%) across 28 views in 23 QML files
- Tab transition 80ms opacity fade (replaced hard-cut _launcherVisible); home icon row repositioned
- Cross-thread signal fix: all 11 PlexLibrary worker signals now use QueuedConnection — root cause of cached data not displaying
- Removed broken sort/filter network calls from PlexMovie/Show Grid/List Component.onCompleted (fixed permanent loading spinner)
- Cache-first offline: sectionLoadFailed signal, _worker_refresh pre-emits cache, plexError cross-thread trampoline, unified toast errors (error banners removed)
- Gamepad suppression wired to all external launchers (setMpvActive → setExternalAppActive); fixes stuck-scroll bug
- WatchScreen Refresh moved inline as last ListView sentinel entry (matches ListenScreen pattern)
- Plex offline cache overhaul: cached server URL for offline client creation, cache-first selectLibrary (synchronous cache load + network backfill), incremental merge-by-rating_key cache saves (every page, never overwrites full cache with partial), poster pre-resolve from disk cache, empty network response ([], 0) guard on all worker functions
- Server URL probe on startup: _setup_client probes primary URL, falls through to remote/relay if unreachable (enables external network access)
- 2,069 tests passing (was 2,017)

---

## CP35 — Plex cache, performance, and test isolation

Task briefs: `misc/coding-team/plex-cache-refresh/`, `misc/coding-team/test-suite-cleanup/`

- Cache-first Plex loading: libraries, on-deck, movies, shows all cached to `plex_cache/` and loaded at startup without network calls
- All Plex cache files consolidated under `~/.config/htpcstation/plex_cache/` (posters, guide, mylist, metadata)
- Poster downloads use Plex `/photo/:/transcode` at 400px — ~10–20× smaller files (896MB → ~50MB)
- Lazy fetch (plex.selectLibrary) now unconditional on all library entry; toggle removed from Settings
- Sort/genre state persisted per section key across app restarts
- Sort state bug fixed: switching between libraries no longer resets the other library's sort
- Async ListenScreen view transitions (fetchArtistDetail, fetchAlbumDetail, etc.) — no more main-thread blocking
- Manual Refresh button added to Plex Media and Plex Music second-level screens
- Test isolation: `conftest.py` autouse fixture redirects all cache I/O to `tmp_path`; real user cache never touched during test runs. 2017 tests passing.

---

## CP34 — UI Layout Refresh: Sub-header hints, keyboard shortcuts, gamepad fixes

Task briefs: `misc/coding-team/subheader-hints/`

- 001–004: Move all button hints from `headerBar` into `statusBar` sub-header on all 17 third-level screens
- 005: Audit fixes — add missing Favorite hint to GameListView; fix GameDetailView gamepad key binding (Qt.Key_F1 → keys.isContext1)
- 006: Favorite retro games from grid and list views; RetroGamesScreen owns toast (matches PcGamesScreen pattern)
- 007–008: Replace footer `actionBar` with `statusBar` sub-header on all detail screens (GameDetailView, PlexMovieDetail, PlexShowDetail)
- 009: Replace F1/F2 keyboard shortcuts with 1/2 number keys (easier on compact HTPC remote keyboards)
- 010–011: Remove all remaining footer `actionBar` instances (SteamGameDetail, MoonlightAppDetail, RecentlyPlayedDetail, LiveTvScreen, SettingsScreen) — zero `actionBar` references remain
- 012: Fix gamepad disconnect segfault (`deleteLater` on notifier + handler); fix hint label flash on connect (`_ready` flag)
- 013: Remove Up-arrow back navigation from all screens (old launcher pattern, now exits tab unexpectedly)
- Misc: Play/pause symbol indicator (▶/■) next to now playing track; global play/pause hint on Now Playing screen; fix ❚❚ font fallback crash; fix settings Up-at-top exits screen; add 16px top padding on second-level screens

---

## CP33 — Homescreen Theme System V1

Task briefs: `misc/coding-team/homescreen-themes/`

- 001: `Config.theme_name` + `SettingsManager.themeName`/`themeDir` (21 new tests)
- 002: `HomeScreen.qml` rewritten as two-level launcher with theme image buttons
- 003: Docs update

---

## Checkpoint History

| CP | Summary | Task briefs |
|---|---|---|
| 1 | M0+M1: shell, retro games | `m0-shell/` (001–004), `m1-games/` (005–014) |
| 2 | Settings UI | `settings/` (025–026) |
| 3 | Plex server discovery, browser extension, M6 hardening | `m2-plex/` (015–020), `m6-hardening-pullforward/` (001–003), `browser-gamepad-extension/` (001–004), `plex-server-discovery/` (001–004) |
| 4 | Plex polish | `plex-polish/` (001–003) |
| 5 | M3 Steam | `m3-steam/` (001–003) |
| 6 | M4 Moonlight | `m4-moonlight/` (001–012) |
| 7 | M5 Home Screen | `m5-home-screen/` (001–006) |
| 8 | Controller mapping, Flatpak gamepad access, Plex modal navigation, button layout | `controller-mapping/` (001–003) |
| 9 | Plex player popup/dropdown navigation, layered cancel, focus stack, stale focus recovery | `plex-player-popups/` (001–005) |
| 10 | Auto-expand minimized player, auto-resume playback, autoplay policy flag | `plex-mini-player-expand/` (001–004) |
| 11 | M5 rich metadata for Steam, grid spacing fix, UI navigation improvements | `m5-rich-metadata/` (001–004) |
| 12 | Listen tab backend | `listen-tab/` (001–006) |
| 13 | Full Listen tab v1 | `listen-tab/` (007–012) |
| 14 | Now Playing view, persistent background playback, global play/pause, sort persistence, tab visibility, Clear Recently Played | `remember-sort/` (001), `phase1-bugs/` (001) |
| 15 | Public release prep, list views for all tabs, LT/RT quick jump, Plex Live TV gamepad navigation | `kernel-headers-dep/` (001–002) |
| 16 | PC Games Favorites, System Cores settings, SYSTEM_DEFAULTS expansion (~130 systems), Plex My List, MPV video player, embedded Live TV guide | `pc-games-favorites/` (001–003), `system-cores-settings/` (001), `system-defaults-expansion/` (001), `plex-watchlist/` (001–002), `plex-mylist/` (001–002), `mpv-player/` (001–004) |
| 17 | UI Refresh 4a: Theme.qml token interface, all hardcoded hex replaced across 26 QML files | `ui-refresh-4a/` (001) |
| 18 | MPV UX overhaul, Plex P0 (timeline, identity, track persistence), Plex P1 (mark watched, transient token, skip intro overlay), poster cache parallelism, Live TV HDHomeRun guide | `mpv-ux-fixes/` (001–015) |
| 19 | Backend optimizations, SSE listener, rating backend, per-row focus memory, in-app Plex PIN login, MPV gamepad input, Live TV improvements | — |
| 20 | libmpv migration: replaced MpvLauncher subprocess + MpvIpc with LibMpvPlayer (python-mpv in-process) | — |
| 21 | Post-libmpv bugfixes, L2/R2 disable | — |
| 22 | Hardening batch 1+2: seek bar, loading/cancel overlay, Alt+F4 recovery | `deferred-batch-1/` (021–024) |
| 23 | Alt+F4 MPV core shutdown recovery + zombie Wayland surface cleanup | — |
| 24 | Hardening batch 3: async detail slots, shared MPV isolation (`_mpv_active` flag) | — |
| 25 | Skip intro auto-seek, WatchScreen header fade, test coverage batch 3 | `skip-intro-header-tests/` |
| 26 | Harden remaining: config wipe prevention (`BrowserLauncher` fix + `Config.save()` guard), `plexError` notifications on Watch+Listen, lyrics zero-duration guard, `_previousView` fix | `harden-remaining/` (001–005) |
| 27 | M1–M3: Music Library UX fix, tab renames (Plex Media/Plex Music), Moonlight dedicated tab, PC Games Steam-only | `m1-m2-tab-renames-music-library-fix/`, `m3-steam-moonlight-tabs/` (001–003) |
| 28 | M5: RetroArch core downloader in install.sh (22 curated cores, ~50MB, default N); fix stale tab labels in installer | `m5-retroarch-core-installer/` (001) |
| 29 | M4: RetroArch core selector — cycle through installed cores, remove TextInput from SystemCoresScreen | `m4-retroarch-core-selector/` (001) |
| 30 | M6: RetroArch hotkey configuration V1 — modifier capture dialog, hotkey mapping, apply to retroarch.cfg | `m6-retroarch-hotkeys/` (001–003) |
| 31 | Fix: modifier capture dialog focus not restored after first use (FocusScope needs focused child) | — |
| 32 | M6→V2: all 12 hotkey rows interactive (tap to assign, hold 3s to clear), rewind settings, duplicate prevention, face button cardinal labels. M8-A/B/C/D: `sdl_resolver.py` ctypes SDL wrapper, dual-record controller mapping (evdev+SDL), dual-record hotkey assignment, mapping wizard Start+Select cancel + hold-to-skip (WIP) | `retroarch-config-v2/` (001–007), `m8-sdl-input/` (008-A–008-D) |
| 33 | Homescreen Theme System V1 | `homescreen-themes/` (001–003) |
| 34 | UI Layout Refresh: sub-header hints, keyboard shortcuts, gamepad fixes | `subheader-hints/` |
| 35 | Plex cache, performance, and test isolation | `plex-cache-refresh/`, `test-suite-cleanup/` |
| 36 | UI Redesign (theme, animations, fades) + Plex cache/offline fixes | `ui-redesign/` (006–009), `fix-context-button-keycodes/` (004–005, 010–012) |
