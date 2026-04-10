# Task 001: Source-Agnostic Playback

## Context

HomeScreen owns the shared `musicPlayer` (Qt MediaPlayer + AudioOutput) and all playback functions. Currently, `_playTrackAtIndex()` (line ~202) and `_playNext()` repeat-one branch (line ~210) hardcode `plex.getTrackStreamUrl(track.mediaKey)` to resolve track URLs. A new Local Music tab will supply `file:///` URLs directly. We need playback to work with any source.

## Objective

Make HomeScreen's playback functions source-agnostic so tracks from any source (Plex, local files, future sources) can play through the shared musicPlayer.

## Scope

**HomeScreen.qml** (`qml/screens/HomeScreen.qml`):
- In `_playTrackAtIndex(idx)`: if `track.streamUrl` is a non-empty string, use it directly as `musicPlayer.source`. Otherwise fall back to `plex.getTrackStreamUrl(track.mediaKey)`.
- In `_playNext()`: same logic in the repeat-one branch (line ~210) where it re-resolves the URL.

**plex_library.py** (`backend/plex_library.py`):
- Every place that builds a track dict (search for `"mediaKey"` in track dict literals) — add a `"streamUrl": ""` field. Plex tracks leave `streamUrl` empty; the QML fallback handles them. This keeps the track dict shape consistent across sources.
- The relevant track-building locations: `_worker_fetch_album_detail`, `_worker_fetch_playlist_tracks`, and any other method that constructs `{"ratingKey": ..., "title": ..., "mediaKey": ...}` dicts for music tracks.

## Non-goals
- Don't change the track dict shape beyond adding `streamUrl`.
- Don't touch lyrics, shuffle, repeat, or any other playback logic.
- Don't add LocalMusicLibrary yet — that's a later task.

## Constraints
- The `streamUrl` field must be a string (empty string when not set, not `undefined`/`null`) so the QML truthiness check `if (track.streamUrl)` works reliably.
- Existing Plex Music playback must work identically after this change. All existing tests must pass.
