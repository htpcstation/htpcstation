# HTPC Station — Resume Document (Checkpoint 36)

> Hand this file to a fresh agent to resume development.
> Deep reference (architecture, full gotchas, gamepad controls): `docs/architecture.md`
> Roadmap and milestone specs: `docs/milestones.md`
> Checkpoint history and task brief archive: `docs/changelog.md`

---

## Documentation Maintenance

**Keep these docs current as you work. Update before committing.**

| Doc | Update when |
|---|---|
| `resume-project.md` | Every checkpoint: bump number, update state/test count, revise next milestone |
| `architecture.md` | Any structural change: new file, renamed signal, removed method, new gotcha discovered |
| `milestones.md` | Milestone completed (mark ✅ + note what actually shipped vs plan), new milestone added |
| `changelog.md` | Every checkpoint: one-line entry + task brief directory reference |

---

## Current State

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. **2,047 tests passing.**

**Tabs (in order):** Retro Games | PC Games | Moonlight | Plex Media | Plex Music | Settings

**What's new since CP35:**
- **UI Redesign (Tasks 006–009):**
  - Theme foundation: neutral dark palette (`#111111`/`#1c1c1c`/`#2a2a2a`), Liberation Sans font, runtime-overridable accent + focus ring colors (persisted to `config.json` `ui` section), rounder focus rings (radius 4→10).
  - Focus scale animation: 1.05× scale with 120ms OutCubic ease on all focusable delegates (22 QML files). Grid delegates use `z:1` when focused. Theme tokens: `focusScale`, `focusScaleDuration`.
  - ListView/GridView highlight centering: `ApplyRange` with `preferredHighlightBegin/End` at 35%/65% across 28 list/grid views (23 QML files). Focused item stays in center third.
  - Tab transition opacity fade: 80ms fade out/in on tab enter/exit (replaced hard-cut `_launcherVisible` toggle). Home icon row repositioned to top-quarter.
- **Plex cache fix — cross-thread signals (Task 010):** Root cause of cache not displaying: all 11 `ThreadPoolExecutor` worker signals were connected with `AutoConnection` (behaves as `DirectConnection` for non-QThread threads in PySide6). Slots ran on worker thread; QML never received model-changed signals. Fixed by adding `QueuedConnection` to all 11 connections.
- **Loading spinner fix (Task 011):** `PlexMovieGrid/List` and `PlexShowGrid/List` called `plex.sortMovies()`/`plex.filterByGenre()` in `Component.onCompleted` — silently dropped because `_current_section_key` was empty. Left `_loading=true` permanently. Removed the redundant calls; `selectLibrary()` already applies saved sort/genre.
- **Cache-first offline display + unified toast errors (Task 012):** Network failure no longer blocks browsing cached libraries. `sectionLoadFailed` signal emitted on network exception; `_worker_refresh` pre-emits cached libraries/on-deck. Error banners removed from WatchScreen and ListenScreen — all errors route to toast. `plexError` now delivered cross-thread via `QMetaObject.invokeMethod` trampoline. ListenScreen gained toast infrastructure.
- **Gamepad suppression for all external launchers (Task 004):** `setMpvActive` renamed to `setExternalAppActive` in `gamepad.py`. Wired to all four launchers (emulators, browser, Moonlight, MPV) — prevents stuck-scroll bug from auto-repeat timers firing into restored UI.
- **WatchScreen inline refresh (Task 005):** Refresh row moved into `libraryList` as last sentinel entry (matches ListenScreen pattern). Removed standalone `refreshItem`, manual focus wiring, and 96px bottom margin.
- **Plex offline cache overhaul (Tasks 001–003):**
  - Cached server URL in `config.json` so `PlexClient` can be created even when plex.tv is unreachable (local server is still reachable).
  - Cache-first `selectLibrary()`: always loads movies/shows/artists from disk cache synchronously, then backfills from network. Works even when `_client is None`.
  - Incremental merge-by-`rating_key` cache saves: every page merges into existing cache (dict snapshot on main thread, disk I/O on `_cache_executor`). A full cache is never overwritten by a partial load.
  - Poster pre-resolve: `_resolve_cached_posters()` checks poster disk cache when loading from JSON cache, preventing unnecessary `_poster_executor` submissions.
  - `sectionLoadFailed` emitted when `_client is None` so QML shows offline toast.
  - Empty network responses `([], 0)` from `get_library_items` (soft failure after retry exhaustion) no longer overwrite cached models — treated as `sectionLoadFailed` in `_worker_load_section`, `_worker_load_more_movies`, and `_worker_load_more_shows`.
  - Server URL probe on startup (Task 004): `_setup_client()` probes the primary URL with a 3s `/identity` check before creating the client. If unreachable (e.g. on external network), falls through to remote/relay URLs from plex.tv resources. Config always caches the local URL for home network use.
  - Offline sort (Task 005): `sortMovies`/`sortShows` sort the in-memory model locally (instant feedback) before submitting network backfill. `getMovieGenres`/`getShowGenres` return empty when server unavailable instead of blocking main thread with retries.
  - Async poster pre-resolve (Task 006): `fetchArtistDetail`, `fetchAlbumDetail`, `fetchRecentAlbums`, and legacy `@Slot` methods (`getArtistAlbums`, `getAlbums`, `getRecentlyAddedAlbums`) no longer download posters sequentially. Replaced `get_poster()` with disk cache pre-resolve (`_cache_path().exists()`). Artist detail with 10 albums loads instantly instead of 10–50s.

**Next milestone:** M7 — Local Music tab V1. See `docs/milestones.md`.

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
python3 main.py           # run directly
./htpcstation.sh          # run via launcher (after install.sh)
python3 -m pytest tests/ -q
bash scripts/check-deps.sh
bash install.sh
```

---

## QML Context Properties

| Name | Type | Purpose |
|---|---|---|
| `keys` | Keys | Semantic key checks, input source, button layout labels |
| `library` | GameLibrary | ROM data, models, launch, favorites |
| `steam` | SteamLibrary | Steam games, models, sort, launch, favorites, recently played |
| `moonlight` | MoonlightLibrary | Moonlight host/app data, models, launch, favorites, recently played |
| `plex` | PlexLibrary | Plex data, models, sort/filter, MPV/browser launch, My List, subtitle IPC, timeline reporting, track persistence, markers, SSE listener |
| `liveTV` | LiveTvLibrary | HDHomeRun guide + streams, MPV launch, guide cache |
| `gamepadManager` | GamepadManager | Raw mode for mapping dialog, device capabilities |
| `networkMonitor` | NetworkMonitor | Periodic connectivity check |
| `settings` | SettingsManager | Config read/write for settings UI, OAuth, PIN login |

---

## Critical Gotchas

The full catalogue is in `docs/architecture.md`. These are the ones most likely to bite first:

**Never use `id: root` in any QML component.** That id belongs to the ApplicationWindow where `vpx()` is defined.

**QML context properties are null on first render.** Guard all bindings: `plex ? plex.model : null`.

**Never name a signal `<propertyName>Changed`.** QML auto-generates those — naming conflict makes the component type "unavailable" with no useful error.

**Only ONE `Component.onCompleted` per QML scope.** QML silently ignores the second one.

**HomeScreen tab array must be built imperatively in `Component.onCompleted`.** Never bind it to `settings.*` — causes cascading focus destruction and app freeze.

**`Loader` recreates the screen on every tab switch.** Trigger data loads in `Component.onCompleted`, not just `onActiveFocusChanged` — focus is only given when the user presses Down from the tab bar.

**python-mpv callbacks run on the mpv event thread.** Never call Qt UI methods directly — use `QMetaObject.invokeMethod` with `QueuedConnection`.

**`_mpvLaunchReady` signal carries 6 args:** `(url, title, start_ms, duration_ms, part_id, intro_end_ms)`. All test mocks must match this signature.

**`Config.save()` refuses to write if in-memory token+server_id are blank but the on-disk file has credentials.** This guard prevents config wipes from rogue `Config()` instantiations. Never construct a second `Config()` instance — pass the existing one.

**`MoonlightScreen` view mode:** child components call `settings.setPcGamesViewMode()` directly. `MoonlightScreen.on_ViewModeChanged` overrides this with `settings.setMoonlightViewMode()`.

---

## Dev Machine

- ThinkPad T480, i5-8350U, Intel UHD 620, Fedora 43, Wayland (GNOME/Mutter)
- ROMs: `~/opencode/ROMs/` (gb, ngpc, sega32x)
- Steam: Flatpak, 5 games
- Moonlight: Flatpak, 1 paired host, 7 apps
- Plex: local server + HDHomeRun FLEX 4K tuner at `192.168.0.2`
- Controller: 8BitDo Micro in D-input mode (Bluetooth)
- HDHomeRun DeviceAuth: in `discover.json` at `http://192.168.0.2/discover.json`
