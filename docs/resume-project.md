# HTPC Station — Resume Document (Checkpoint 29)

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

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. **1,713 tests passing.**

**Tabs (in order):** Retro Games | PC Games | Moonlight | Plex Media | Plex Music | Settings

**What's new since CP26:**
- M1: Music Library dropdown in Settings now populates immediately after first Plex sign-in
- M2: Watch → "Plex Media", Listen → "Plex Music" (display labels only, config keys unchanged)
- M3: Moonlight split into its own tab (`MoonlightScreen.qml`). PC Games is now Steam-only and GOG-ready. Each tab has its own Favorites and Recently Played. `MoonlightLibrary` gained `getRecentlyPlayed()` / `clearRecentlyPlayed()`. All `steam.setMoonlight*` injection removed.
- M5: `install.sh` Phase 6 — optional RetroArch core downloader. 22 curated cores from libretro buildbot nightly, ~50MB total, default N, non-fatal per-core failures. Also fixed stale "Watch"/"Listen" labels in installer.
- M4: `SystemCoresScreen` TextInput replaced with Left/Right cycle-through-installed-cores. `SettingsManager.getAvailableCores()` scans `cores_directory` for `*.so` files.

**Next milestone:** M6 — RetroArch hotkey configuration V1. See `docs/milestones.md`.

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
