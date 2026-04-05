# HTPC Station — Milestones

Ordered by priority. Each milestone is self-contained and can be handed to the coding team as a unit.

---

## M1 — Music Library UX fix ✅ Done (CP27)

Music Library dropdown in Settings now populates immediately after first Plex sign-in. `SettingsScreen` calls `plex.refresh()` when `getMusicLibraries()` returns empty, and re-evaluates the dropdown when `librariesModelChanged` fires via `_librariesVersion` counter.

---

## M2 — Rename tabs ✅ Done (CP27)

Watch → "Plex Media", Listen → "Plex Music". Display labels only — config keys (`show_watch`, `show_listen`) unchanged.

---

## M3 — Moonlight dedicated tab ✅ Done (CP27)

**What shipped (differs from original plan):** PC Games tab stays as the home for local launchers (Steam + future GOG). Moonlight splits into its own dedicated tab. `PcGamesScreen.qml` was not retired — it was simplified to Steam-only.

- `MoonlightScreen.qml`: new tab with sources (Recently Played, Favorites, Apps), app grid/list, detail view
- `PcGamesScreen.qml`: Moonlight stripped out, Steam-only, `SteamSourceListModel` kept and GOG-ready
- `MoonlightLibrary`: gained `getRecentlyPlayed()` and `clearRecentlyPlayed()`
- All `steam.setMoonlight*` injection removed from `SteamLibrary` and `main.py`
- Config: `show_moonlight_tab` + `moonlight_view_mode` added. `show_pc_games` unchanged.
- Tab order: Retro Games | PC Games | Moonlight | Plex Media | Plex Music | Settings

---

## M4 — RetroArch core selector ✅ Done (CP29)

`TextInput` edit mode replaced with Left/Right cycle-through-installed-cores. `SettingsManager.getAvailableCores()` scans `cores_directory` for `*.so` files (sorted, excludes `.so.zip`/`.info`). Delegate shows `"◀  core  ▶"` on current row when cores available. Header hint updates dynamically. Empty state shows toast "No cores installed — run install.sh". Saves immediately on cycle via existing `setSystemCore()`.

---

## M5 — RetroArch core downloader (install.sh) ✅ Done (CP28)

New Phase 6 in `install.sh`. Gated on Retro Games tab selected + RetroArch Flatpak installed. Prompts with default N. Downloads 22 curated cores from `https://buildbot.libretro.com/nightly/linux/x86_64/latest/<core>.so.zip` into `~/.var/app/org.libretro.RetroArch/config/retroarch/cores/`. Skips already-installed cores. Non-fatal per-core failures. Total download ~50MB (sizes were much smaller than estimated — largest core is ppsspp at ~8MB).

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
