# HTPC Station

## Project Overview

HTPC Station turns an old mini PC into a couch-friendly entertainment center. It presents a single fullscreen interface — fully navigable with a gamepad — that brings together retro game emulation, PC gaming via Steam, game streaming via Moonlight, Plex video browsing, and Plex music playback in one place. Rather than playing media or running emulators itself, HTPC Station acts as a launcher and library browser: it handles browsing, artwork, and metadata, then hands off to RetroArch, Steam, Moonlight, and MPV when you press Play. The interface is designed for 1080p output and runs well on low-power hardware such as Intel J5005-class mini PCs (for example, the Dell Wyse 5070).

---

## What You Can Do Today

### Retro Games

- Browse your ROM collection with box art and video previews.
- View game metadata: rating, genre, number of players, and description.
- Mark games as favorites and access them in a dedicated Favorites collection.
- Browse by Last Played or All Games collections.
- Sort games A-Z, Z-A, or by most recently played.
- Switch between Grid and List views from the sort menu. List view shows a preview panel with artwork, metadata, and description alongside the game list.
- Launch any game directly into RetroArch.
- Play stats (play count, last played, total time) are tracked automatically.
- Configure the RetroArch core for each system individually from Settings.

### PC Games (Steam)

- Auto-discovers all installed Steam games — no manual setup needed.
- Poster artwork is downloaded automatically.
- Rich metadata from the Steam Store: description, genre, developer, Metacritic score, and more.
- Grid and List views available for Steam, Moonlight, and Recently Played sources.
- Mark Steam and Moonlight games as favorites. A PC Favorites collection groups them together.
- Sort and launch games directly.

### Game Streaming (Moonlight)

- Stream games from a Sunshine or Apollo host on your local network.
- Artwork is auto-fetched from Steam for recognized game titles.
- Custom artwork is supported for apps that don't match automatically.
- Host availability is shown so you know if your streaming PC is reachable.
- Launch directly into a streaming session.

### Watch (Plex)

- Browse Plex movie and TV show libraries with posters and metadata.
- Continue Watching section with progress bars for in-progress titles.
- TV show detail view with season tabs and per-episode watched indicators.
- Sort by name, date, year, or rating; filter by genre.
- Grid and List views for movies, shows, and Continue Watching.
- **My List** — a local personal playlist. Press X on any movie, show, or episode to add or remove it. My List appears at the bottom of the Watch tab library list.
- Play any title directly in **MPV** for hardware-accelerated local playback. When resuming a partially watched title, a dialog offers to resume from where you left off or start from the beginning.
- Press Y during MPV playback to open a subtitle track selector.
- **Live TV** — an embedded channel guide powered by your HDHomeRun tuner and Plex DVR. Browse all channels with current and next program information. Press A to start watching a channel directly in MPV.
- Plex Web browser launch is available as a fallback (toggle in Settings).
- Multi-user Plex Home support, including content restrictions for managed and kids profiles.

### Listen (Plex Music)

- Browse artists, albums, playlists, and recently added music from your Plex music library.
- Grid and List views for the artist browser, with sort support (A-Z, Z-A).
- Full Now Playing screen with album art, track info, and playback controls.
- Music keeps playing in the background while you browse other tabs.
- Press X from any tab to pause or resume playback.
- A persistent "now playing" indicator appears in the top-right corner of the screen.

### Controller and Navigation

- Full gamepad navigation throughout the entire interface.
- Configurable button mapping for 14 inputs — remap any button to suit your controller.
- Standard and Alternate button layouts to match different controller styles.
- Keyboard navigation works everywhere as well.
- A visible focus ring always shows where you are on screen.
- Buttons auto-repeat when held down.
- Quick scroll with LT/RT (or PageUp/PageDown on keyboard): jumps to the next letter when sorted alphabetically, or skips 10 items otherwise.
- Action hints update automatically based on whether you are using a gamepad or keyboard.
- Press Start+Select together to close the Plex browser and return to HTPC Station.

### Settings

- Configure ROM paths and RetroArch settings.
- Set the RetroArch core for each individual system.
- Sign in to Plex with OAuth (no manual token entry needed).
- Select your Plex server and switch between Plex Home users.
- Choose video player: MPV (default, hardware-accelerated) or Plex Web browser.
- Set your Moonlight host and browser command.
- Remap your controller or choose a button layout.
- Toggle video snap autoplay and adjust the preview delay.
- Show or hide the network status indicator.
- Choose which tabs are visible (takes effect after restarting the app).
- All changes are saved automatically.

---

## Getting Started

### What You Need

- A Linux PC (x86_64). Works well on low-power hardware like the Dell Wyse 5070 or any Intel J5005-class machine. Also runs fine on regular desktops and laptops.
- A gamepad or a keyboard.
- Python 3.10 or newer.
- **For retro games:** RetroArch installed (Flatpak recommended), plus ROMs with Batocera/Knulli/EmulationStation scraped metadata (`gamelist.xml` and artwork). HTPC Station does not scrape ROMs — prepare your library first.
- **For Steam games:** Steam installed (Flatpak or native).
- **For game streaming:** Moonlight installed (Flatpak recommended) and a Sunshine or Apollo host.
- **For Plex video playback:** MPV installed (`sudo dnf install mpv` or equivalent). Hardware acceleration requires VA-API drivers — see the dependency checker output for your specific hardware and distro.
- **For Plex Live TV:** An HDHomeRun tuner connected through Plex DVR.
- **For Plex music and browser fallback:** Brave browser (Flatpak recommended).
- **For Plex:** A Plex account with access to a Plex Media Server. Local network direct-play is preferred.

### Installation

```bash
git clone https://github.com/htpcstation/htpcstation.git
cd htpcstation
```

Before installing Python dependencies, check that system prerequisites are in place:

```bash
bash scripts/check-deps.sh
```

This checks for Python 3.10+, kernel headers, MPV, VA-API hardware decode drivers, FFmpeg codec support, optional Flatpak apps (RetroArch, Steam, Moonlight, Brave), and gamepad input devices. Each failed check prints the specific install command for your distro and hardware.

Then install Python packages:

```bash
pip install -r requirements.txt
```

### Running

```bash
python3 main.py
```

The app launches fullscreen. All configuration is done from the Settings tab inside the app.

### Running Tests

```bash
python3 -m pytest tests/ -q
```

The suite currently covers over 1,450 backend tests. If you want those tests to use your own Moonlight host, Plex server URL, or other personal values, create a git-ignored JSON file with overrides:

1. Copy `tests/local_overrides.sample.json` to `tests/local_overrides.json` (or `tests/.local/test_overrides.json`).
2. Replace the sample data with your real values.
3. Optional: set `HTPC_TEST_OVERRIDES=/full/path/to/file.json` to store it elsewhere.

```json
{
  "moonlight_hostname": "DESKTOP-MYPC",
  "moonlight_local_ip": "192.168.0.5",
  "moonlight_manual_ip": "10.0.0.5",
  "moonlight_public_remote_ip": "203.0.113.10",
  "plex_server_url": "http://192.168.0.5:32400"
}
```

The tests automatically load these overrides via `tests/local_overrides.py`, so your personal network details stay local while the public repository keeps sanitized defaults.

---

## Using HTPC Station

**Tabs:** The top bar has tabs — Retro Games, PC Games, Watch, Listen, and Settings. Navigate to the tab bar and use Left/Right to switch between them. You can hide tabs you don't use in Settings; changes take effect after restarting the app.

**Navigation:** The D-pad or arrow keys move focus around the screen. The bright focus ring shows where you are. Press Down from the tab bar to enter the content area below.

**Launching content:** Press Accept (A on a gamepad, or Enter on a keyboard) to select or launch something. Press Cancel (B or Escape) to go back.

**Sorting and view mode:** Press Y (or F2) to open the sort menu in any grid or list view. From this menu you can also switch between Grid and List views. Your sort and view preferences are remembered between sessions.

**Favorites (Retro Games):** Press X (or F1) on a game to toggle it as a favorite. Favorites appear in their own collection at the top of the system list.

**Favorites (PC Games):** Press X on any Steam or Moonlight game to toggle it as a favorite. A PC Favorites source appears at the top of the PC Games source list.

**My List (Watch):** Press X on any movie, show, or episode to add or remove it from My List. My List appears at the bottom of the Watch tab library list and launches directly in MPV.

**Video playback:** By default, movies and shows play in MPV with hardware acceleration. If a title has a saved position, a dialog asks whether to resume or start from the beginning. Press Y during playback to open the subtitle track selector. To switch to Plex Web browser playback, go to Settings → Plex → Video Player.

**Live TV:** Select Live TV from the Watch tab library list to open the channel guide. Each row shows the channel logo, number, and current and next program. Press A to start watching. Channels without a matching HDHomeRun tuner show "Not available."

**Music playback:** Start playing music in the Listen tab, then navigate anywhere — music keeps playing in the background. Press X from any tab to pause or resume. The current track name is shown in the top-right corner.

**Plex browser:** When using browser playback mode, a browser window opens for playback. Use the gamepad to control playback (play/pause, seek, navigate menus). Press Start+Select together to close the browser and return to HTPC Station.

**Controller mapping:** Go to Settings, then Controller, then Map Controller to remap your gamepad. The dialog walks you through each button one at a time.

**Custom artwork:** You can add your own poster images for Moonlight apps or Steam games:
- Moonlight: drop images into `~/.config/htpcstation/moonlight/artwork_custom/` named after the app (e.g., `desktop.jpg`, `steam-big-picture.png`).
- Steam: drop images into `~/.config/htpcstation/steam/artwork_custom/` named after the Steam app ID (e.g., `440.jpg` for Team Fortress 2).

Custom images always override auto-downloaded artwork.

**MPV gamepad bindings:** MPV uses a bundled `input.conf` at `~/.config/htpcstation/mpv/input.conf`. The file is created automatically on first launch and updated when new bindings are added. You can edit it manually — your changes are preserved across updates as long as the version header is current.

| Button | MPV Action |
|---|---|
| A | Play / Pause |
| B | Quit (return to HTPC Station) |
| D-pad Left/Right | Seek ±10 seconds |
| D-pad Up/Down | Volume ±5 |
| LT / RT | Previous / Next chapter |
| LB | Cycle audio track |
| X | Open subtitle selector (via HTPC Station overlay) |
| Y | Show playback progress |
| Start | Quit |

### Controller Reference

| Button | Action |
|---|---|
| D-pad / Arrow keys | Navigate |
| A / Enter | Select / Launch |
| B / Escape | Back / Cancel |
| X / F1 | Favorite / My List toggle / Play-Pause (music) |
| Y / F2 | Sort / View menu; Subtitle selector (during MPV playback) |
| LT / RT (PgUp/PgDn) | Quick scroll (next letter or ±10 items) |
| Start / F10 | Quit dialog |
| Start + Select / Alt + F4 | Close Plex browser |

---

## Current Limitations

- Changing which tabs are visible requires restarting the app.
- HTPC Station does not scrape ROM metadata. You need another scraper to create `gamelist.xml` files and download artwork before HTPC Station can display your retro game library.
- Plex browser playback (when enabled) happens in a kiosk window. To exit back to HTPC Station, press Start+Select on your gamepad (or Alt+F4 on a keyboard).
- Continue Watching is hidden for managed and kids Plex profiles. This is a Plex platform limitation with no known workaround.
- Moonlight host pairing must be done through Moonlight's own interface. You can open it from Settings by pressing "Open Moonlight."
- Large Plex music playlists (over 1,000 tracks) are hidden to avoid performance issues.
- Live TV requires an HDHomeRun tuner connected through Plex DVR. Channels not available on the tuner show "Not available" in the guide.
- AV1 video content requires hardware decode support (Intel Gen 12+ / Tiger Lake or newer). On older hardware, AV1 plays via software decode and may stutter on high-bitrate files.
- MPV gamepad bindings use standard Linux evdev button names. If your controller uses non-standard mappings, edit `~/.config/htpcstation/mpv/input.conf` manually.
- Only tested on Linux x86_64 with Xorg and Wayland (via XWayland for the Qt app; MPV uses native Wayland context).

---

## Future Goals

- Streaming service integration (YouTube, Netflix, and others) via the browser extension framework.
- Tab management improvements so hiding or showing tabs does not require a restart.
- Richer music features: shuffle, repeat, a seek bar, and volume control.
- Metadata (descriptions, genres) for Moonlight apps pulled from Steam.
- Plex search.
- Mark watched/unwatched in Plex.
- First-run setup wizard.
- Standalone emulator support (Dolphin, PCSX2, etc.) for systems without a libretro core.

---

## Tech Stack

For those interested in what's under the hood:

| Component | Technology |
|---|---|
| Application framework | Qt 6 / QML with PySide6 (Python) |
| Target hardware | Intel J5005-class (Gemini Lake) or better |
| Target display | 1920x1080 fullscreen, Xorg or Wayland |
| Emulator backend | RetroArch via Flatpak |
| PC game launch | Steam URI protocol (`steam://rungameid/`) |
| Game streaming | Moonlight CLI (Flatpak) |
| Media browsing | Plex Media Server API |
| Video playback | System MPV with VA-API hardware decode (direct Plex stream URLs) |
| Live TV | HDHomeRun direct streams via Plex DVR + Plex cloud EPG |
| Music playback | Qt MediaPlayer + AudioOutput (direct Plex audio streams) |
| Gamepad input | evdev with synthetic Qt key events |
| Browser gamepad | Chromium extension (Manifest V3) with Gamepad API |
| Configuration | JSON (`~/.config/htpcstation/config.json`) |

---

## Credits and Acknowledgments

HTPC Station was developed with the assistance of AI coding agents, coordinated through OpenCode. It builds on the work of many excellent open-source projects: Qt and PySide6, RetroArch, Steam, Moonlight, Plex, MPV, Brave, Pegasus, and ES-DE. Thank you to all the developers and communities behind these tools.

---

## Bug Reports

Report bugs via [GitHub Issues](https://github.com/htpcstation/htpcstation/issues).

---

## License

HTPC Station is released under the [MIT License](LICENSE).
