# Task 009 — Remove dead synchronous @Slot methods

## Context

Eight `@Slot` methods in `plex_library.py` are no longer called from QML —
they've been replaced by async `fetch*` equivalents. They make synchronous
network calls and would block the main thread if ever called. Remove them
to prevent accidental use and reduce code surface.

## Objective

Delete the following methods from `backend/plex_library.py`:

1. `getStreamInfo` — replaced by `fetchStreamInfo`
2. `getWatchHistory` — replaced by `fetchWatchHistory`
3. `getAlbum` — replaced by `fetchAlbumDetail`
4. `getArtistAlbums` — replaced by `fetchArtistDetail`
5. `getAlbums` — replaced by `fetchAlbumDetail`
6. `getPlaylists` (sync version) — replaced by `fetchPlaylists`
7. `getPlaylistTracks` (sync version) — replaced by `fetchPlaylistTracks`
8. `getTracks` — replaced by `fetchAlbumDetail`
9. `getRecentlyAddedAlbums` (sync version) — replaced by `fetchRecentAlbums`

## Constraints

- Verify each method has zero QML callers by grepping all `.qml` files for
  the method name before deleting.
- Do NOT delete `getArtist` — it is still called from `PlexArtistList.qml`.
- Do NOT delete `getTrackStreamUrl` — it is still called from `HomeScreen.qml`
  (and is not actually a network call).
- Do NOT delete `getMovieGenres` / `getShowGenres` — still called from QML.
- Remove any associated internal helper methods that become unused after
  deletion, but be careful — some helpers may be shared with async methods.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
  Tests that call the deleted methods directly should be removed or updated.
