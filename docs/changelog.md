# HTPC Station — Changelog

One entry per checkpoint. Task briefs live under `~/opencode/misc/coding-team/`.

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
