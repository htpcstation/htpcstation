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

## M6 — RetroArch hotkey configuration (V1) ✅ Done (CP30) — V2 ✅ Done (CP32)

**V1 (CP30):**
- `backend/retroarch_config.py`: `read_cfg`/`write_cfg`, `build_hotkey_cfg`
- `RetroarchHotkeysScreen.qml`: modifier row + read-only hotkey rows + Apply button
- `ModifierCaptureDialog.qml`: raw mode capture, 10s timeout

**V2 (CP32):**
- All 12 hotkey rows interactive: tap to assign, hold 3s to clear (uses release events — raw mode now emits `value=0`)
- 12 hotkeys: Save/Load State, Fast Forward (Toggle/Hold), Rewind, Open Menu, Screenshot, Show FPS, Next/Prev Save Slot, Pause Toggle, Exit Emulator
- `HOTKEY_CFG_KEYS` triple keys per action (`_btn`/`_axis`/`_hat`); `build_hotkey_cfg` writes correct key type from SDL record
- Rewind settings: enable/disable, buffer size (20–500 MB), granularity (1–32 frames) — cycle rows in screen, written to retroarch.cfg on Apply
- Duplicate button prevention across modifier and all hotkey rows
- Face button labels honour standard/alternate layout with cardinal positions (e.g. "A (East)", "X (North)")
- `hotkey_modifier_sdl`, `hotkey_modifier_evdev`, `hotkey_mapping` (SDL record dicts), `rewind_*` persisted in config.json
- Toast warning if controller mapping wizard hasn't been run before hotkey assignment

**V3 scope (deferred):** per-system cfg overrides (shader, integer scaling, etc.).

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

## M8 — Dual-record input mapping (evdev + SDL) ✅ Done (CP32) — M8-A/B/C/D

**What:** Extend the controller mapping system to record both evdev and SDL representations of every input simultaneously. Each consumer reads the half it needs — evdev for HTPC Station Qt key injection and in-process MPV, SDL for RetroArch config and the browser gamepad extension. This makes hotkey assignment and controller mapping work correctly for any device in the SDL GameControllerDB — XInput, Switch Pro Controller, DualSense, etc.

**Architecture (as shipped):**

Each mapping entry stores a dual record:
```json
{
  "evdev": {"type": "axis", "code": 17, "value": -1},
  "sdl":   {"type": "hat",  "sdl_hat": 0, "dir": "up"},
  "also":  []
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

**What shipped (M8-A through M8-D):**

- **M8-A (CP32):** `backend/sdl_resolver.py` — ctypes wrapper, probes `libSDL2-2.0.so.0` → `libSDL2-2.0.so` → `libSDL2.so` → `libSDL3.so.0` → `libSDL3.so` at import. `SdlResolver.open()` opens the matching SDL joystick by name, enumerates axes/buttons/hats via `SDL_GameControllerGetBindFor*` API, builds internal lookup tables. `resolve(evtype, code, value)` returns SDL record dict. `seed_from_controller_mapping()` populates a primary lookup from the saved mapping (source of truth). Lifecycle: `open()` on `startRawMode()`, `close()` on `stopRawMode()`. Module-level singleton `resolver`.
- **M8-B (CP32):** Dual-record controller mapping. `DEFAULT_MAPPING` updated to `{"evdev": {...}, "sdl": None}` format. `load_mapping()` migrates old single-record format on load. `saveControllerMapping()` resolves SDL records at save time (before `stopRawMode()`). Co-firing `also` array records simultaneous events from dual-reporting devices (D-input triggers fire axis + button simultaneously). `build_evdev_lookup()` reads only the `evdev` half. `build_web_gamepad_mapping()` reads only the `sdl` half.
- **M8-C (CP32):** Dual-record hotkey assignment. `HOTKEY_CFG_KEYS` has triple keys per action (`_btn`/`_axis`/`_hat`). `build_hotkey_cfg()` writes the correct key type from the SDL record type. `setHotkeyModifier()` and `setHotkeyActionByEvdev/ByAxis()` resolve SDL records via `SdlResolver`. Duplicate prevention via `_store_hotkey_sdl()` eviction. Face button labels honour standard/alternate layout with cardinal positions (e.g. "A (East)", "X (North)").
- **M8-D (CP32):** Controller mapping wizard improvements. Start+Select combo cancel. `getControllerActionEvdevCodes()` slot. Cancel hint adapts to gamepad vs keyboard input source (`keys.useGamepadLabels`). Hold-to-skip: stores pending event on press, records on release if timer still running; fires skip if held 3s. **Known issue (fix pending):** for dual-reporting inputs (D-input triggers fire axis event first, then button event), the button event hits the `else` branch and calls `_recordInput` immediately instead of waiting for release. Fix: button events arriving while `_holdSkipCode !== -1` should be ignored.

**Existing saved mappings** (evdev-only format) are migrated transparently on load.

**Unblocked:** D-pad and trigger hotkey assignment. XInput support (future). Switch Pro Controller support (future).

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
| UI Refresh 4b/4c — theme switcher + palette presets | Theme foundation shipped (CP36: neutral palette, runtime accent/focus ring colors, Liberation Sans). Remaining: preset palette picker UI, user-facing theme switcher in Settings. |
| Plex search | New navigation flow |
| Moonlight rich metadata | Deferred from original roadmap |
| XInput controller support | M8 done — needs real-device test + any per-device quirk fixes |
| Switch Pro Controller support | M8 done — needs real-device test + any per-device quirk fixes |
