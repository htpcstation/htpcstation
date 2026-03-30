# HTPC Station

## Project Overview

HTPC Station turns an old mini PC into a couch-friendly entertainment center. It presents a single fullscreen interface — fully navigable with a gamepad — that brings together retro game emulation, PC gaming via Steam, game streaming via Moonlight, Plex video browsing, and Plex music playback in one place. Rather than playing media or running emulators itself, HTPC Station acts as a launcher and library browser: it handles browsing, artwork, and metadata, then hands off to RetroArch, Steam, Moonlight, and Plex Web when you press Play. The interface is designed for 1080p TVs and runs well on low-power hardware such as Intel J5005-class mini PCs (for example, the Dell Wyse 5070).

---

## What You Can Do Today

### Retro Games

- Browse your ROM collection with box art and video previews.
- View game metadata: rating, genre, number of players, and description.
- Mark games as favorites and access them in a dedicated Favorites collection.
- Browse by Last Played or All Games collections.
- Sort games A-Z, Z-A, or by most recently played.
- Launch any game directly into RetroArch.
- Play stats (play count, last played, total time) are tracked automatically.

### PC Games (Steam)

- Auto-discovers all installed Steam games — no manual setup needed.
- Poster artwork is downloaded automatically.
- Rich metadata from the Steam Store: description, genre, developer, Metacritic score, and more.
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
- Launch any title into Plex Web for playback with a single button press.
- Live TV support via HDHomeRun tuners connected through Plex DVR.
- Multi-user Plex Home support, including content restrictions for managed and kids profiles.

### Listen (Plex Music)

- Browse artists, albums, playlists, and recently added music from your Plex music library.
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
- Action hints update automatically based on whether you are using a gamepad or keyboard.
- Press Start+Select together to close the Plex browser and return to HTPC Station.

### Settings

- Configure ROM paths and RetroArch settings.
- Sign in to Plex with OAuth (no manual token entry needed).
- Select your Plex server and switch between Plex Home users.
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
- A gamepad (Xbox-style recommended) or a keyboard.
- Python 3.10 or newer.
- **For retro games:** RetroArch installed (Flatpak recommended), plus ROMs with ES-DE scraped metadata (`gamelist.xml` and artwork). HTPC Station does not scrape ROMs — use ES-DE to prepare your library first.
- **For Steam games:** Steam installed (Flatpak or native).
- **For game streaming:** Moonlight installed (Flatpak recommended) and already paired with a Sunshine or Apollo host.
- **For Plex:** A Plex Media Server running on your network.
- **For Plex playback:** Brave browser (Flatpak recommended). Other Chromium-based browsers may work.

### Installation

```bash
git clone https://github.com/htpcstation/htpcstation.git
cd htpcstation
pip install PySide6 evdev requests
```

### Running

```bash
python3 main.py
```

The app launches fullscreen. All configuration is done from the Settings tab inside the app.

### Running Tests (optional)

```bash
python3 -m pytest tests/ -q
```

There are over 1,000 tests covering the backend.

---

## Using HTPC Station

**Tabs:** The top bar has tabs — Retro Games, PC Games, Watch, Listen, and Settings. Use the bumper buttons (LB/RB) or the left and right arrow keys to switch between them. You can hide tabs you don't use in Settings; changes take effect after restarting the app.

**Navigation:** The D-pad or arrow keys move focus around the screen. The bright focus ring shows where you are. Press Down from the tab bar to enter the content area below.

**Launching content:** Press Accept (A on a gamepad, or Enter on a keyboard) to select or launch something. Press Cancel (B or Escape) to go back.

**Sorting:** Press Y (or F2) to open the sort menu in any grid view. Your sort preference is remembered between sessions.

**Favorites (Retro Games):** Press X (or F1) on a game to toggle it as a favorite. Favorites appear in their own collection at the top of the system list.

**Music playback:** Start playing music in the Listen tab, then navigate anywhere — music keeps playing in the background. Press X from any tab to pause or resume. The current track name is shown in the top-right corner.

**Plex browser:** When you launch a Plex title, a browser window opens for playback. Use the gamepad to control playback (play/pause, seek, navigate menus). Press Start+Select together to close the browser and return to HTPC Station.

**Controller mapping:** Go to Settings, then Controller, then Map Controller to remap your gamepad. The dialog walks you through each button one at a time.

**Custom artwork:** You can add your own poster images for Moonlight apps or Steam games:
- Moonlight: drop images into `***REMOVED***.config/htpcstation/moonlight/artwork_custom/` named after the app (e.g., `desktop.jpg`, `steam-big-picture.png`).
- Steam: drop images into `***REMOVED***.config/htpcstation/steam/artwork_custom/` named after the Steam app ID (e.g., `440.jpg` for Team Fortress 2).

Custom images always override auto-downloaded artwork.

### Controller Reference

| Button | Action |
|---|---|
| D-pad / Arrow keys | Navigate |
| A / Enter | Select / Launch |
| B / Escape | Back / Cancel |
| X / F1 | Favorite (retro games) / Play-Pause (music) |
| Y / F2 | Sort menu |
| LB / RB (PageUp/PageDown) | Switch tabs |
| LT / RT (Home/End) | Page scroll |
| Start / F10 | Quit dialog |
| Start + Select | Close Plex browser |

---

## Current Limitations

- Changing which tabs are visible requires restarting the app.
- HTPC Station does not scrape ROM metadata. You need ES-DE or another scraper to create `gamelist.xml` files and download artwork before HTPC Station can display your retro game library.
- Plex playback happens in a browser window. To exit back to HTPC Station, press Start+Select on your gamepad (or Alt+F4 on a keyboard).
- Continue Watching is hidden for managed and kids Plex profiles. This is a Plex platform limitation with no known workaround.
- Moonlight host pairing must be done through Moonlight's own interface. You can open it from Settings by pressing "Open Moonlight."
- Large Plex music playlists (over 1,000 tracks) are hidden to avoid performance issues.
- The Plex Live TV guide is not yet fully navigable with a gamepad.
- Per-system emulator core configuration is not yet available (coming soon).
- Only tested on Linux x86_64 with Xorg. Wayland is not yet supported.

---

## Future Goals

- Streaming service integration (YouTube, Netflix, and others) via the browser extension framework.
- Tab management improvements so hiding or showing tabs does not require a restart.
- Richer music features: shuffle, repeat, a seek bar, and volume control.
- Metadata (descriptions, genres) for Moonlight apps pulled from Steam.
- PC game favorites.
- Plex watchlist and search.
- First-run setup wizard.
- Wayland support.

---

## Tech Stack

For those interested in what's under the hood:

| Component | Technology |
|---|---|
| Application framework | Qt 6 / QML with PySide6 (Python) |
| Target hardware | Intel J5005-class (Gemini Lake) or better |
| Target display | 1920x1080 fullscreen, Xorg |
| Emulator backend | RetroArch via Flatpak |
| PC game launch | Steam URI protocol (`steam://rungameid/`) |
| Game streaming | Moonlight CLI (Flatpak) |
| Media browsing | Plex Media Server API |
| Media playback | Plex Web via Brave browser (kiosk mode) |
| Music playback | Qt MediaPlayer + AudioOutput (direct Plex audio streams) |
| Gamepad input | evdev with synthetic Qt key events |
| Browser gamepad | Chromium extension (Manifest V3) with Gamepad API |
| Configuration | JSON (`***REMOVED***.config/htpcstation/config.json`) |

---

## Credits and Acknowledgments

HTPC Station was developed with the assistance of AI coding agents, coordinated through OpenCode. It builds on the work of many excellent open-source projects: Qt and PySide6, RetroArch, Steam, Moonlight, Plex, Brave, and ES-DE (for ROM scraping and metadata). Thank you to all the developers and communities behind these tools.
