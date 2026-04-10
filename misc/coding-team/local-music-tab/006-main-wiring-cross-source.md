# Task 006: Main.py Wiring + Cross-Source Playback Takeover

## Context

All backend (`LocalMusicLibrary`), settings, and QML are implemented. This task wires `LocalMusicLibrary` into `main.py` as a QML context property and ensures cross-source playback works (local music and Plex music share the same musicPlayer — starting one stops the other).

## Objective

Register `LocalMusicLibrary` in main.py and verify cross-source playback takeover is handled correctly.

## Scope

### main.py

1. **Import:** Add `from backend.local_music_library import LocalMusicLibrary` (near the other backend imports, line ~70).

2. **Instantiate:** After the `config` is created and before `engine.load()`, create:
   ```python
   local_music = LocalMusicLibrary(config)
   engine.rootContext().setContextProperty("localMusic", local_music)
   ```
   Place it near the other library instantiations (after plex_library, before or after steam/moonlight — order doesn't matter).

### Cross-source playback takeover

This is already handled by HomeScreen's architecture:
- There is ONE `musicPlayer` (MediaPlayer) on HomeScreen.
- `_playAlbum()` sets `musicPlayer.source` to a new URL and calls `play()`. This automatically stops whatever was playing before.
- Local music tracks have `streamUrl` (file:// URI). Plex tracks fall back to `plex.getTrackStreamUrl()`.
- When the user plays a local track, `musicPlayer.source` changes to a file:// URL → Plex stream stops.
- When the user plays a Plex track, `musicPlayer.source` changes to a Plex URL → local stream stops.

No additional code is needed for takeover — it's inherent in the single-player design. Verify this is the case by reading the code; don't add unnecessary stop/reset logic.

## Non-goals
- Don't change any backend, QML, or settings code
- Don't add shutdown hooks for LocalMusicLibrary (it has no persistent connections to close — just a ThreadPoolExecutor that Python cleans up)

## Constraints
- The `localMusic` context property name must match what `LocalMusicScreen.qml`, `LocalArtistGrid.qml`, and `LocalArtistList.qml` reference.
