# HTPC Station — Hardening Backlog

Generated from a full codebase audit. Grouped into batches by priority.

---

## Batch 1 — Crashes and stuck UI ✅ Done

| ID | File | Issue |
|----|------|-------|
| C1 | `plex_library.py` | `_mpvLaunchReady.emit()` fixed: 8 args → 6 |
| C3 | `config.py` | `assert` → guard + warning in `set_plex_player` |
| C4 | `plex_library.py` | `_save_my_list` wrapped in `try/except OSError` |
| M1 | `mpv_launcher.py` | timeout path emits `_emit_finished` so overlay clears |
| M3 | `HomeScreen.qml` | `InvalidMedia` handled separately — no silent auto-advance |
| H6 | `plex_library.py` | `_artists_cache_path` uses `CONFIG_DIR` |
| M9 | `config.py` | `config.save()` wrapped in `try/except OSError` |

---

## Batch 2 — Visible UX bugs ✅ Done

| ID | File | Issue |
|----|------|-------|
| H7 | `WatchScreen.qml` | `plex.plexError` wired to error banner (auto-dismiss 5s; auth = persistent) |
| H8 | `WatchScreen.qml` | `_showDetailOrigin` tracks entry point; B from show detail returns to correct view |
| M7 | — | Dropped — no loop-back is correct UX |
| M5 | — | Dropped — no Up-escape is correct UX for Listen submenus |
| H4 | `WatchScreen.qml` | Three `target: plex` Connections blocks merged into one |

**Additional fixes in this batch (post-commit):**
- Alt+F4 (GNOME/Wayland): libmpv `quit` destroys core → `_on_shutdown` callback → `_recreate_player` on main thread → `terminate()` cleans zombie Wayland surface → fresh `set_wid()` restores playback capability
- `launch()` / `launch_live_tv()` force-stop zombie player instead of silently ignoring

**Additional fixes in this batch:**
- Loading overlay: 20s hard timeout, B to cancel, `_mpvLaunched` / `_cancelledDuringLoad` flags prevent video playing after cancel
- `vid = "no"` during buffering prevents flash on cancel
- `kill()` non-blocking (dispatches `player.stop()` off-thread)
- `focusRestoreTimer` + `_routeFocus()` guards prevent focus loss after overlay hides
- Resume dialog: overlay stays as backdrop; `loadingOverlayTimer` skips hide while dialog visible
- My List → show detail → B: returns to My List with saved focus index
- Alt+F4 during MPV (GNOME/Wayland): `_show_window_after_mpv` hides + recreates Qt surface after 150ms
- Seek bar: `MediaPlayer.position =` (not `.seek()`); `Item` with `focus: true` (not `FocusScope`); mouse drag via `MouseArea`

---

## Batch 3 — Harder / higher blast radius ✅ Done

| ID | File | Line(s) | Issue |
|----|------|---------|-------|
| H2 | `plex_library.py` | Done | `getMovie`/`getShow`/`getSeasons`/`getEpisodes` → `fetchMovie`/`fetchShow`/`fetchSeasons`/`fetchEpisodes` async slots; signals `movieReady`/`showReady`/`seasonsReady`/`episodesReady`; old sync slots removed |
| H3 | `WatchScreen.qml` | Done | 20s `loadingTimeoutTimer`, B to cancel, `_mpvLaunched`/`_cancelledDuringLoad` flags |
| C2 | `plex_library.py` | Deferred | Race window is ~1 event-loop tick; not a real stall in practice |
| H5/M8 | `plex_library.py` / `live_tv_library.py` | Done | `_mpv_active` flag in both libraries gates all MPV signals — Plex and Live TV signals no longer cross-fire |

---

## Remaining items ✅ Done (CP26)

| ID | Area | Resolution |
|----|------|------------|
| H1 | `plex_library.py` | Zero-duration guard in `getLyrics`: emits `lyricsUnavailable` immediately, skips LRCLIB fetch |
| M2 | `WatchScreen.qml` / `ListenScreen.qml` | `plexError` banner on Watch + Listen tabs; transient toast during active MPV playback on Watch |
| M4 | `ListenScreen.qml` | `_previousView` updated in `onCurrentViewChanged` (not just in `_goToNowPlaying`) — always tracks last non-nowplaying view |
| T1–T3 | tests | `test_poster_cache.py`, `test_plex_timeline_reporter.py`, `test_config_edge_cases.py` added in CP25 |
| T4 | `live_tv_library.py` | N/A — cache has no staleness logic by design. Warm start serves cache instantly then always overwrites with fresh fetch. Nothing to test. |
| T5 | `plex_library.py` | Covered by `test_harden_batch1.py` C1 test (updated for 6-arg signal in CP25) |
| T6 | `plex_library.py` | Covered by `test_config_edge_cases.py` (CP25) |
| G1 | `architecture.md` | Fixed in CP25 — `_mpvLaunchReady` correctly documented as 6 args |
| G2 | `resume-project.md` | Kept current at each checkpoint |

---

## Deferred / Won't fix

| ID | Note |
|----|------|
| C2 | Race window is ~1 event-loop tick; not a real stall in practice |
| M6 | Album list Up dead end at first item — B is the standard back gesture, acceptable |
| M2 (server offline mid-playback, no reconnect) | Recovery path exists; toast now shown. Automatic reconnect deferred — requires backend work. |
