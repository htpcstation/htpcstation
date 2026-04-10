# Task 002: Move Now-Playing View to HomeScreen

## Context

The now-playing view (~600 lines, ListenScreen.qml lines 1065-1668) currently lives inside ListenScreen as the `"nowplaying"` view state. It already reads all state from HomeScreen properties (`_nowPlayingTrack`, `_playbackAlbumData`, `musicPosition`, `musicDuration`, `_shuffleEnabled`, `_repeatMode`, `_lyricsLines`, etc.) and calls HomeScreen functions (`_playPrev`, `_playNext`, `_togglePlayPause`, `_toggleShuffle`, `_cycleRepeat`, `_seekBy`, `_seekTo`, `_formatDuration`). It has no dependency on ListenScreen-specific state.

We're moving it to HomeScreen level so it can be shared by both Plex Music and the upcoming Local Music tab (and any future music source).

## Objective

Extract the now-playing view from ListenScreen into a HomeScreen-level overlay. Any tab can show it via `homeScreen._showNowPlaying()`. B/Escape returns focus to wherever the user was before.

## Scope

### HomeScreen.qml

1. **Add state properties:**
   - `property bool _nowPlayingVisible: false`
   - `property Item _nowPlayingReturnItem: null` — the item to return focus to when hiding

2. **Add functions:**
   - `_showNowPlaying()`: saves `contentLoader.item` (or current focus item) as `_nowPlayingReturnItem`, sets `_nowPlayingVisible = true`, gives focus to the now-playing view.
   - `_hideNowPlaying()`: sets `_nowPlayingVisible = false`, returns focus to `_nowPlayingReturnItem`.

3. **Add the now-playing overlay** — place it after the content area Item (line ~445) and before ClockDisplay (line ~447) so it renders on top. Copy the entire `FocusScope` from ListenScreen lines 1065-1668, with these adjustments:
   - Remove `visible: listenScreen.currentView === "nowplaying"` → use `visible: homeScreen._nowPlayingVisible`
   - Change B/Escape handler (line 1078): instead of `listenScreen.currentView = listenScreen._previousView || "menu"`, call `homeScreen._hideNowPlaying()`
   - All `homeScreen.` references stay as-is (they already reference HomeScreen)
   - All `root.vpx()` references stay as-is
   - All `Theme.*` references stay as-is
   - All `keys.*` references stay as-is
   - The `lyricsView` inner id and all other ids need no prefix — they won't collide since the old code in ListenScreen is being removed.

4. **Expose `_showNowPlaying` as a property/function** so child screens (loaded via contentLoader) can call `homeScreen._showNowPlaying()`.

### ListenScreen.qml

1. **Remove the entire now-playing FocusScope** (lines 1065-1668).

2. **Replace `_goToNowPlaying()` function** (line 47-49): change from `currentView = "nowplaying"` to `homeScreen._showNowPlaying()`.

3. **Remove `"nowplaying"` from `_routeFocus()`** (line ~317): remove the `else if (currentView === "nowplaying")` branch.

4. **Remove `_previousView` property** (line 45) — the return-focus mechanism is now in HomeScreen.

5. **Remove the line** `_previousView = currentView` (line ~353) that was set before navigating to nowplaying.

6. **Remove `"nowplaying"` from the `currentView` doc comment** at the top of the file.

7. **The "Now Playing" menu item** (line ~437, ~491, ~513-514): keep it in the menu, but its action should call `homeScreen._showNowPlaying()` instead of setting `currentView`. The visibility condition `homeScreen.nowPlayingTrack !== ""` stays.

### Tests

Existing tests that mock or test now-playing behavior may need updates if they reference ListenScreen's `"nowplaying"` view state. Search tests for `"nowplaying"` and `_goToNowPlaying` and `_previousView` and update accordingly. The key change: `_goToNowPlaying()` now calls `homeScreen._showNowPlaying()` instead of setting `currentView = "nowplaying"`.

## Non-goals
- Don't change any playback logic (shuffle, repeat, lyrics, etc.)
- Don't add LocalMusicScreen yet
- Don't refactor the now-playing UI itself (just move it)
- Don't change the now-playing indicator (top-right "♫ Track Name") — it stays where it is

## Constraints
- The now-playing overlay must sit above the content loader in z-order so it covers the tab content.
- Focus must return cleanly: B from now-playing → back to whatever tab view was active.
- The `_showNowPlaying()` must work whether called from a tab screen (contentLoader.item) or from the launcher. Guard for null `contentLoader.item`.
- **Never use `id: root`** in the now-playing overlay — that id belongs to ApplicationWindow.
- **Only ONE `Component.onCompleted` per QML scope** — HomeScreen already has one.
