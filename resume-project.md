# HTPC Station — Resume Document (Checkpoint 17)

> Hand this file to a fresh agent to resume development.
> For full codebase structure, gotchas, architecture notes, and history: `docs/architecture.md`

---

## Current State

Fullscreen gamepad-navigable HTPC launcher. Qt6/QML + PySide6. All 5 tabs working: Retro Games, PC Games, Watch, Listen, Settings. **1,452 tests passing.**

**What's new since Checkpoint 16:**
- UI Refresh 4a: Theme.qml token interface complete. All hardcoded hex colors replaced with semantic tokens across 26 QML files. Zero hardcoded colors remain outside Theme.qml.

**What's new since Checkpoint 15:**
- PC Games Favorites, System Cores settings, SYSTEM_DEFAULTS ~130 systems
- Plex My List, MPV video player (VA-API, Wayland, resume, subtitle overlay)
- Embedded Live TV guide (EPG + HDHomeRun), hardware-aware check-deps

---

## Roadmap

| # | Item | Notes |
|---|---|---|
| 1 | ~~F3 — PC Games Favorites~~ | ✅ Done |
| 2 | ~~C2 — System Cores settings~~ | ✅ Done |
| 3 | Moonlight rich metadata | Deferred — nearly free when resumed (steam_app_id already in artwork_index.json) |
| 4 | ~~F4 — Plex My List~~ | ✅ Done |
| 5 | ~~UI Refresh 4a — token interface + Theme.qml palettes~~ | ✅ Done |
| 6 | On-screen keyboard | Needed for gamepad-only wizard text input |
| 7 | X1 — First-run setup wizard | Built on new tokens + OSK |
| 8 | UI Refresh 4b/4c — QML token replacement + theme switcher | High blast radius, phase separately |
| 9 | Listen tab enhancements | Shuffle/repeat, seek bar, volume |
| 10 | Mark watched/unwatched (Plex) | Single API write + toggle |
| 11 | Plex search | New navigation flow |
| 12 | Custom user-defined collections | Needs scoping |
| 13 | GOG/Epic Games Store | Needs spike first |
| 14 | Standalone emulator support (Dolphin, PCSX2) | Additive launcher extension |
| 15 | Gamepad extension: YouTube/Netflix | Browser extension work |
| 16 | Plex token encryption / OS keyring | Security hardening |

---

## Stack

| | |
|---|---|
| Framework | Qt 6 / QML + PySide6 (Python 3.10+) |
| Target | Linux x86_64, Xorg or Wayland, Intel J5005-class or better |
| Video playback | System MPV (`/usr/bin/mpv`), VA-API hwdec, direct Plex stream URLs |
| Live TV | HDHomeRun direct streams, Plex cloud EPG (`discover.provider.plex.tv`) |
| Emulator | RetroArch via Flatpak |
| PC games | Steam URI (`steam://rungameid/`), Moonlight CLI (Flatpak) |
| Plex music | Qt MediaPlayer + AudioOutput (direct Plex audio streams) |
| Browser | Brave Flatpak (music playback, MPV fallback) |
| Gamepad | evdev → synthetic QKeyEvent injection |
| Config | `~/.config/htpcstation/config.json` |
| MPV config | `~/.config/htpcstation/mpv/input.conf` (versioned, auto-written) |

---

## Commands

```bash
# Run
python3 main.py

# Test
python3 -m pytest tests/ -q

# Check dependencies
bash scripts/check-deps.sh
```

---

## QML Context Properties

| Name | Type | Purpose |
|---|---|---|
| `keys` | Keys | Semantic key checks, input source, button layout labels |
| `library` | GameLibrary | ROM data, models, launch, favorites |
| `steam` | SteamLibrary | Steam/Moonlight games, models, sort, launch, favorites |
| `moonlight` | MoonlightLibrary | Moonlight host/app data, models, launch |
| `plex` | PlexLibrary | Plex data, models, sort/filter, MPV/browser launch, My List, subtitle IPC |
| `liveTV` | LiveTvLibrary | EPG channels, HDHomeRun streams, MPV launch |
| `gamepadManager` | GamepadManager | Raw mode for mapping dialog, device capabilities |
| `networkMonitor` | NetworkMonitor | Periodic connectivity check |
| `settings` | SettingsManager | Config read/write for settings UI, OAuth |

---

## Critical Gotchas (read before touching these areas)

**QML context properties are null on first render.** Guard all bindings: `plex ? plex.model : null`. Applies to `liveTV`, `steam`, `settings`, etc.

**Never use `id: root` in any QML component.** That id belongs to the ApplicationWindow where `vpx()` is defined.

**Never name a signal `<propertyName>Changed`.** QML auto-generates those and the conflict makes the component type "unavailable".

**HomeScreen tab arrays must be built imperatively, not via bindings.** Binding to `settings.showRetroGamesTab` causes cascading focus destruction and freezes the app. Build in `Component.onCompleted` only.

**Only ONE `Component.onCompleted` per QML scope.** QML silently fails with "Property value set multiple times" if you have two.

**Plex managed user tokens get 401 from the media server.** Always use the admin token for server API calls. User token is only for browser deep links.

**MPV on Wayland needs `--hwdec=vaapi-copy` and `--gpu-context=wayland`.** On Xorg use `--hwdec=vaapi` and `--gpu-context=x11`. `MpvLauncher._gpu_context()` and `_hwdec_mode()` auto-detect from `XDG_SESSION_TYPE`.

**Fedora ships codec-restricted packages.** `ffmpeg-free` → swap for `ffmpeg` (RPM Fusion). `libva-intel-media-driver` → swap for `libva-intel-driver` (RPM Fusion). `check-deps.sh` detects and reports these.

**`flatpak kill <app_id>` required to close Brave.** `QProcess.kill()` only kills the wrapper, not the sandboxed browser.

**Moonlight QSettings INI fields are all lowercase.** `hostname`, `localaddress`, `uuid` — not camelCase.

**Theme.qml: use semantic tokens, never `_palette` vars.** `_bg`, `_accent`, etc. are internal. QML files reference `colorBackground`, `colorAccent`, etc. `colorPrimary` and `colorSecondary` are kept as aliases for the 255 existing usages — rename them in 4b/4c.

---

## Dev Machine

- ThinkPad T460, i5-8350U (Kaby Lake-R), Intel UHD 620, Fedora 43, Wayland
- ROMs: `~/opencode/ROMs/` (gb, ngpc, sega32x)
- Steam: Flatpak, 5 games
- Moonlight: Flatpak, 1 paired host, 7 apps
- Plex: local server + HDHomeRun FLEX 4K tuner at `192.168.0.80`
- Controller: 8BitDo Micro in D-input mode (D-pad as ABS_X/ABS_Y, no analog sticks)
