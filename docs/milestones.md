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

## M6 — RetroArch hotkey configuration (V1) ✅ Done (CP30)

- `backend/retroarch_config.py`: `EVDEV_TO_SDL` table (8BitDo Micro D-input), `read_cfg`/`write_cfg` (flat INI, preserves existing keys), `build_hotkey_cfg` (10 hotkeys + `input_enable_hotkey_btn`, None→"nul")
- `RetroarchHotkeysScreen.qml`: modifier row + 10 read-only hotkey rows + Apply button. Accessible from Settings → RetroArch section.
- `ModifierCaptureDialog.qml`: raw mode capture (evdev `rawInput` signal), 10s timeout, all exit paths stop raw mode. Home button (BTN_MODE/316) confirmed working on 8BitDo Micro D-input.
- Hotkey mapping derived from controller mapping on first run; stored as explicit dict in config for V2 per-row overrides without schema change.
- `hotkey_modifier_evdev`, `hotkey_mapping`, `retroarch_cfg_path` persisted under `retroarch` section in config.json.

**V2 scope (deferred):** per-row hotkey overrides, rewind settings, per-system cfg overrides.

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

## M8 — Dual-record input mapping (evdev + SDL)

**What:** Extend the controller mapping system to record both evdev and SDL representations of every input simultaneously. Each consumer reads the half it needs — evdev for HTPC Station Qt key injection and in-process MPV, SDL for RetroArch config and the browser gamepad extension. This makes hotkey assignment and controller mapping work correctly for any device in the SDL GameControllerDB — XInput, Switch Pro Controller, DualSense, etc.

**Why now:** The current evdev→SDL translation is hardcoded for the 8BitDo Micro D-input via `EVDEV_TO_SDL`. D-pad and trigger hotkey assignment are blocked on this. The controller mapping wizard has the same limitation. The fix is to record SDL indices at capture time (when the device is connected and queryable) rather than translating at apply time via a static table.

**Architecture:**

Each mapping entry changes from a single evdev record to a dual record:
```json
{
  "evdev": {"type": "axis", "code": 17, "value": -1},
  "sdl":   {"type": "hat",  "hat": 0,   "dir": "up"}
}
```

Consumer routing:
| Consumer | Reads | Reason |
|---|---|---|
| `gamepad.py` Qt key injection | `evdev` half | Injects raw evdev codes as QKeyEvents |
| `LibMpvPlayer` (in-process) | `evdev` half | Uses Qt key injection path |
| `build_hotkey_cfg()` → retroarch.cfg | `sdl` half | RetroArch uses SDL internally |
| `build_web_gamepad_mapping()` → browser extension | `sdl` half | Web Gamepad API uses SDL indices |
| Hotkey modifier (`input_enable_hotkey_btn`) | `sdl` half only | RetroArch concept; HTPC launcher never uses it |

**Scope:**

- **M8-A: SDL resolver** — `backend/sdl_resolver.py`. ctypes wrapper that locates and loads the SDL library at runtime (see SDL library caveats below). Given a connected evdev device, opens the matching SDL joystick (matched by name/GUID), enumerates its buttons/axes/hats, and resolves an evdev event `(type, code, value)` to an SDL record `{"type": "button"|"axis"|"hat", ...}`. The GameControllerDB is compiled into the SDL library — no local cache or network fetch needed. Lifecycle: open on `GamepadManager.startRawMode()`, close on `stopRawMode()`. Graceful fallback (returns `None`) if SDL unavailable, no device connected, or device not in SDL database.

**Effort:** Large (7–9 tasks).

**Caveats:**

- **SDL library portability — must work on any distro.** The SDL library name and location vary:
  - Fedora 43: `sdl2-compat` (SDL2 API shim over SDL3) at `/usr/lib64/libSDL2-2.0.so.0`
  - Ubuntu/Debian: real `libSDL2-2.0.so.0` from `libsdl2-2.0-0` package
  - Arch: SDL3 natively (`libSDL3.so.0`); SDL2 available separately
  - The resolver must probe a candidate list in order: `libSDL2-2.0.so.0`, `libSDL2-2.0.so`, `libSDL2.so`, `libSDL3.so.0`, `libSDL3.so`. Load the first one that works via `ctypes.CDLL`. If none found, log a warning and operate in evdev-only mode (SDL half = `null` for all inputs).
  - `sdl2-compat` on Fedora is a drop-in SDL2 API replacement — function signatures are identical. Smoke-test during M8-A to confirm no edge cases.
  - The GameControllerDB is compiled into whichever SDL library is loaded — no distro ships it as a separate file. No local cache or network fetch needed on any distro.

- **SDL init:** Initialise with `SDL_INIT_JOYSTICK` only. PySide6 does not use SDL on Linux — no conflict. Call `SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1")` so SDL receives events while the Qt window has focus.

- **SDL joystick matching:** Prefer GUID match against the connected evdev device; fall back to name match; fall back to first joystick if only one is connected.

- **Fallback when SDL can't resolve:** Store `"sdl": null`. Consumers that need SDL write `nul` to retroarch.cfg and show `"Button <N>"` label. The evdev half is always recorded regardless.

- **Existing saved mappings** (evdev-only format) are migrated on load: wrap the existing record as the `evdev` half, set `sdl` to `null`. No data loss.

- Per-system cfg overrides remain deferred until after M8-C.

**Unblocks:** D-pad and trigger hotkey assignment. XInput support. Switch Pro Controller support.

---

## M9 — Local Videos tab (V1)

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
| RetroArch config V3 — per-system cfg overrides | Per-system retroarch.cfg overrides (shader, integer scaling, etc.). Blocked on M8-C. |
| RetroArch config V4 — full Batocera parity | Shader presets, integer scaling, run-ahead, netplay defaults |
| On-screen keyboard | Prerequisite for first-run wizard (text input without physical keyboard) |
| First-run setup wizard | Guided config for new installs |
| UI Refresh 4b/4c — token replacement + theme switcher | High blast radius; do after tab restructure is stable |
| Plex search | New navigation flow |
| Moonlight rich metadata | Deferred from original roadmap |
| XInput controller support | Blocked on M8 |
| Switch Pro Controller support | Blocked on M8 |
