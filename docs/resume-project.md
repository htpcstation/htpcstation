# HTPC Station — Resume Document (Checkpoint 35)

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

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. **2,017 tests passing.**

**Tabs (in order):** Retro Games | PC Games | Moonlight | Plex Media | Plex Music | Settings

**What's new since CP34:**
- **Plex cache system:** All content (libraries, on-deck, movies, shows, artists) cached to `~/.config/htpcstation/plex_cache/`. Loads instantly on cold boot without network calls.
- **Poster optimisation:** Downloads via Plex `/photo/:/transcode` at 400px wide — ~10–20× smaller than full-res (896MB → ~50MB for 1366 posters).
- **Lazy fetch:** `plex.selectLibrary()` called unconditionally on every library entry; sort/genre state preserved per section key and persisted across restarts.
- **Sort bug fix:** Switching between libraries no longer resets the other library's sort state. Sort is keyed per section, not shared globally.
- **Async ListenScreen:** All view transitions (artist detail, album, playlists, recently added) are non-blocking — no more main-thread HTTP calls.
- **Manual Refresh button:** Added to Plex Media and Plex Music second-level screens.
- **Test isolation:** `conftest.py` autouse fixture redirects all cache I/O to `tmp_path`. Real user cache is never touched during test runs. Removed one-time migration test.

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
