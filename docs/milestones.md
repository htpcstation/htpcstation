# HTPC Station — Milestones

Ordered by priority. Each milestone is self-contained and can be handed to the coding team as a unit.

---

## M1 — Music Library UX fix ✅ Ready to implement

**What:** After first Plex sign-in, the Music Library dropdown in Settings is empty until the user visits the Watch tab (which triggers `plex.refresh()` and populates `_libraries_model`). `getMusicLibraries()` reads from that model, so it returns nothing until the model is loaded.

**Fix:** When the Music Library select row is opened in Settings and `plex.getMusicLibraries()` returns empty, trigger `plex.refresh()` so the model loads. Alternatively, expose a `plex.librariesReady` signal that Settings listens to and re-queries on.

**Scope:** `SettingsScreen.qml` (or `PlexLibrary` + `SettingsScreen`). No config changes.

**Effort:** Small (1 task).

---

## M2 — Rename tabs ✅ Ready to implement

**What:** Display label changes only. Config keys (`show_watch`, `show_listen`) are unchanged.

| Old label | New label |
|---|---|
| Watch | Plex Media |
| Listen | Plex Music |

**Scope:** `HomeScreen.qml` tab definitions only (lines ~34–37). No backend, no config, no key renames.

**Effort:** Trivial (bundle with M1 or any other task).

---

## M3 — Steam and Moonlight dedicated tabs

**What:** Split `PcGamesScreen` into two independent tabs. Each tab gets its own Favorites and Recently Played. The combined cross-library lists (`RecentlyPlayedGrid/List` mixing Steam + Moonlight, `PC Favorites`) are dropped.

**Current state:**
- `PcGamesScreen` uses `SteamSourceListModel` with sources: Steam, Moonlight hosts (injected via `setMoonlightSources()`), Recently Played (unified), PC Favorites (unified).
- `steam.getRecentlyPlayed()` returns a unified Steam + Moonlight list.
- `steam.getFavorites()` + `moonlight.getFavorites()` are merged in QML for PC Favorites.

**Target state:**
- **Steam tab** (`SteamScreen.qml`): Steam games only. Favorites = `steam.getFavorites()`. Recently Played = Steam-only recently played (filter out Moonlight entries from `getRecentlyPlayed()`).
- **Moonlight tab** (`MoonlightScreen.qml`): Moonlight hosts + apps. Favorites = `moonlight.getFavorites()`. Recently Played = Moonlight play history from `moonlight_play_history.py`.
- `PcGamesScreen.qml` retired.
- `SteamSourceListModel` no longer needs `setMoonlightSources()` — Steam tab is Steam-only.
- `steam.getRecentlyPlayed()` simplified to Steam-only (remove Moonlight injection).
- `MoonlightLibrary` gets a `getRecentlyPlayed()` slot (reads `moonlight_play_history.py`).

**Config:** Add `show_steam_tab` and `show_moonlight_tab` keys (replacing `show_pc_games`). Migration: if `show_pc_games` is true in existing config, set both new keys to true.

**Effort:** Medium (4–5 tasks).

**Caveats:**
- `RecentlyPlayedGrid/List/Detail` QML components are currently shared between Steam and Moonlight — they can stay shared (parameterized by model), just sourced separately per tab.
- `setMoonlightSources()` wiring in `main.py` and `MoonlightLibrary` refresh callback needs cleanup.

---

## M4 — RetroArch core selector: dropdown replacing text entry

**What:** Replace the `TextInput` in `SystemCoresScreen` with a dropdown that lists `.so` files found in `cores_directory`. User picks from installed cores; no manual typing.

**Backend:** Add `SettingsManager.getAvailableCores() -> list[str]` — scans `config.cores_directory` for `*.so` files, returns sorted filenames. Empty list if directory missing or no cores installed.

**QML:** Replace `TextInput` + edit mode in `SystemCoresScreen` with a cycle/select component (same pattern as Video Player setting). Show `"(none)"` if no cores installed with a hint to use the installer.

**Effort:** Small-medium (2 tasks: backend scan + QML replacement).

**Caveats:**
- If `cores_directory` is empty or no `.so` files exist, show a graceful empty state ("No cores installed — run install.sh").
- The current text entry allowed typing arbitrary paths; the dropdown only shows what's installed. This is intentional — manual entry was error-prone.

---

## M5 — RetroArch core downloader (install.sh)

**What:** Optional step in `install.sh`: "Download recommended RetroArch cores?" Downloads a curated set of cores from the libretro buildbot nightly (`https://buildbot.libretro.com/nightly/linux/x86_64/latest/`), unzips them into the Flatpak cores directory.

**Curated defaults (one core per system family, covers the systems in SYSTEM_DEFAULTS):**

| Core file | Systems |
|---|---|
| `gambatte_libretro.so` | gb, gbc, sgb, gb2players, gbc2players |
| `mgba_libretro.so` | gba |
| `mesen_libretro.so` | nes, fds, sgb |
| `snes9x_libretro.so` | snes, snes-msu1, sufami, satellaview |
| `mupen64plus_next_libretro.so` | n64, n64dd |
| `melonds_libretro.so` | nds |
| `genesis_plus_gx_libretro.so` | megadrive, segacd, mastersystem, gamegear, sg1000, pico |
| `picodrive_libretro.so` | sega32x |
| `mednafen_psx_hw_libretro.so` | psx |
| `mednafen_pce_libretro.so` | pce, pcengine, pcenginecd, supergrafx |
| `mednafen_ngp_libretro.so` | ngp, ngpc |
| `mednafen_wswan_libretro.so` | wonderswan, wonderswancolor, wswan, wswanc |
| `mednafen_saturn_libretro.so` | saturn |
| `flycast_libretro.so` | dreamcast, naomi, naomi2, atomiswave |
| `fbneo_libretro.so` | neogeo, fbneo |
| `ppsspp_libretro.so` | psp |
| `pcsx2_libretro.so` | ps2 |
| `vice_x64_libretro.so` | c64 |
| `bluemsx_libretro.so` | msx1, msx2, msx2+, msxturbor, colecovision |
| `fuse_libretro.so` | zxspectrum |
| `dosbox_pure_libretro.so` | dos |
| `scummvm_libretro.so` | scummvm |

**Installer logic:**
1. Check if RetroArch Flatpak is installed.
2. Prompt: "Download recommended RetroArch cores? (~200MB) [y/N]"
3. For each core: skip if `.so` already exists in cores dir. Download `.so.zip`, unzip, delete zip.
4. Report success/failure per core. Non-fatal — missing cores are skipped with a warning.

**Effort:** Medium (1 task, bash only).

**Caveats:**
- Buildbot URL format: `https://buildbot.libretro.com/nightly/linux/x86_64/latest/<core>.so.zip`
- Requires `curl` or `wget` + `unzip` — add to `check-deps.sh` check if download option selected.
- Flatpak sandbox: cores must go to `~/.var/app/org.libretro.RetroArch/config/retroarch/cores/`.
- Some cores (pcsx2, dolphin) are large (50–100MB each) — consider making them opt-in within the prompt.

---

## M6 — RetroArch hotkey configuration (V1)

**What:** Read and write RetroArch's `retroarch.cfg` to map HTPC Station's button layout to RetroArch hotkeys. V1 scope: hotkeys only (no per-system overrides, no rewind settings yet).

**retroarch.cfg location:** `~/.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg` (Flatpak). Expose as a configurable path in Settings (default auto-detected from Flatpak path).

**Hotkey mappings to expose (V1):**

| HTPC Station action | RetroArch cfg key | Notes |
|---|---|---|
| Accept (A/East) | `input_menu_toggle_btn` | Open RetroArch menu |
| Cancel (B/South) | `input_exit_emulator_btn` | Quit to HTPC Station |
| Context1 (X/North) | `input_save_state_btn` | Save state |
| Context2 (Y/West) | `input_load_state_btn` | Load state |
| Left Shoulder | `input_state_slot_decrease_btn` | State slot − |
| Right Shoulder | `input_state_slot_increase_btn` | State slot + |
| Start | `input_pause_toggle_btn` | Pause |
| Select | `input_screenshot_btn` | Screenshot |
| L2/Left Trigger | `input_rewind_btn` | Hold to rewind (requires rewind enabled) |
| R2/Right Trigger | `input_fast_forward_btn` | Fast forward |

Button values in `retroarch.cfg` are joypad button indices (0-based). HTPC Station's evdev codes map to RetroArch joypad indices via the controller mapping.

**Backend:** New `backend/retroarch_config.py` — reads/writes `retroarch.cfg` (simple key=value INI, no sections). Exposes `read_hotkeys()` and `write_hotkeys(mapping: dict)`. Handles missing file gracefully (creates with defaults).

**SettingsManager:** New slots `getRetroarchHotkeys()` and `setRetroarchHotkeys(mapping)`. New config key `retroarch_cfg_path` (default: Flatpak path, auto-detected).

**QML:** New sub-screen `RetroarchHotkeysScreen.qml` accessible from Settings. Shows each action with its current button assignment. A/Accept to edit a row cycles through available buttons. Inherits button layout from HTPC Station's current mapping.

**Effort:** Large (5–6 tasks).

**Caveats:**
- RetroArch joypad button indices depend on the SDL gamepad mapping, not evdev codes directly. Need to map HTPC Station's evdev codes → SDL button indices for the specific controller. For the 8BitDo Micro D-input: BTN_EAST(305)→0, BTN_SOUTH(304)→1, BTN_NORTH(307)→3, BTN_WEST(308)→2, BTN_TL(310)→4, BTN_TR(311)→5, BTN_SELECT(314)→6, BTN_START(315)→7.
- `retroarch.cfg` uses `nul` for unbound. Write `nul` when clearing a binding.
- V2 (rewind settings, per-system overrides) is a follow-up milestone. Note it here so the backend module is designed with extension in mind.
- The hotkey enable button (`input_enable_hotkey_btn`) should be set to Select so hotkeys don't fire during normal gameplay — include this as a non-editable default.

---

## M7 — Local Music tab (V1)

**What:** New "Local Music" tab. Plays music from a local directory tree structured as `Artists/Albums/tracks`. V1 uses directory names as metadata (no tag scanning). Playback via existing Qt `MediaPlayer` + `AudioOutput` (same as Plex Music tab).

**Directory structure expected:**
```
<local_music_dir>/
  Artist Name/
    Album Name/
      01 - Track Name.mp3
      02 - Track Name.flac
      ...
```

**Backend:** New `backend/local_music_library.py`. Scans directory tree on `refresh()`. Builds models: artists (directory names), albums (subdirectory names), tracks (audio files). Supported extensions: `.mp3`, `.flac`, `.ogg`, `.wav`, `.m4a`, `.aac`. Exposes QML-compatible list models and slots matching the Plex Music pattern where possible.

**Config:** New `local_music_directory` key in `config.json`. Exposed in Settings as a text field (same pattern as `romDirectory`). New `show_local_music_tab` visibility toggle.

**QML:** New `LocalMusicScreen.qml`. Reuse the ListenScreen navigation pattern (menu → artists → albums → tracks → now playing). Reuse `HomeScreen`'s `MediaPlayer` + `AudioOutput` for playback — wire up the same `_playTrack` / `_playNext` / `_playPrev` slots.

**Effort:** Large (5–6 tasks).

**Caveats:**
- V2 (tag scanning via mutagen or similar) is a future item — design the data model so `artist`/`album`/`title` fields can be populated from tags later without changing the QML interface.
- If `local_music_directory` is not set or empty, the tab shows a "Set your music directory in Settings" placeholder.
- Track ordering: sort by filename (natural sort — `01 - ...`, `02 - ...`).
- No lyrics, no timeline reporting, no Plex integration.

---

## M8 — Local Videos tab (V1)

**What:** New "Local Videos" tab. Plays local video files via `LibMpvPlayer`. V1: flat or two-level (folder/file) directory browse. No metadata scraping, no posters — filename only.

**Directory structure (V1):**
```
<local_videos_dir>/
  Movie Title (2023).mkv
  TV Shows/
    Show Name/
      S01E01 - Episode Title.mkv
```

**Backend:** New `backend/local_video_library.py`. Scans directory on `refresh()`. Builds a flat model of video files + folders. Supported extensions: `.mkv`, `.mp4`, `.avi`, `.mov`, `.m2ts`, `.ts`. No metadata beyond filename and path.

**Config:** New `local_videos_directory` key. Settings text field. New `show_local_videos_tab` toggle.

**QML:** New `LocalVideosScreen.qml`. Two-level browse: top level shows folders + loose files; selecting a folder shows its contents. Selecting a file launches `LibMpvPlayer` (same path as Watch tab, minus Plex-specific resume/timeline logic). Reuse the loading overlay and cancel pattern from `WatchScreen`.

**Effort:** Medium-large (4–5 tasks).

**Caveats:**
- No resume position tracking in V1 (no viewOffset equivalent). Add in V2.
- No poster/thumbnail in V1 — filename display only.
- MPV playback reuses `LibMpvPlayer` directly; no Plex timeline reporter, no transient token.
- V2 additions: resume tracking (local JSON), TMDb/OMDB metadata scraping, poster cache.

---

## Deferred / Future

| Item | Notes |
|---|---|
| Local Music V2 — tag scanning | Add mutagen dependency, async scan, populate artist/album/title/duration from ID3/Vorbis tags |
| Local Videos V2 — resume + metadata | Local resume JSON, TMDb scraping, poster cache |
| RetroArch config V2 — rewind + per-system overrides | Build on M6 backend; add rewind enable/buffer-size, per-system cfg overrides |
| RetroArch config V3 — full Batocera parity | Shader presets, integer scaling, run-ahead, netplay defaults |
| On-screen keyboard | Prerequisite for first-run wizard (text input without physical keyboard) |
| First-run setup wizard | Guided config for new installs |
| UI Refresh 4b/4c — token replacement + theme switcher | High blast radius; do after tab restructure is stable |
| Plex search | New navigation flow |
| Moonlight rich metadata | Deferred from original roadmap |
