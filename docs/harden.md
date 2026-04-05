# HTPC Station — Hardening Backlog

Generated from a full codebase audit. Grouped into batches by priority.

---

## Batch 1 — Crashes and stuck UI (fix first)

| ID | File | Line(s) | Issue |
|----|------|---------|-------|
| C1 | `plex_library.py` | 1173 | `_mpvLaunchReady.emit()` passes 8 args to 5-arg signal — crashes on no-stream-URL path |
| C3 | `config.py` | 362 | `assert` in `set_plex_player` removed by `-O` — invalid value silently persists |
| C4 | `plex_library.py` | 2063–2066 | `_save_my_list` has no `try/except` — unhandled `OSError` on main thread |
| M1 | `mpv_launcher.py` | 163–178 | `wait_until_playing` timeout leaves loading overlay stuck forever — emit `processFinished` on timeout |
| M3 | `HomeScreen.qml` | 125–129 | `EndOfMedia` fires on failed load — bad URL auto-advances silently through queue |
| H6 | `plex_library.py` | 2086 | `_artists_cache_path` hardcodes `~/.config/htpcstation` instead of `CONFIG_DIR` |
| M9 | `config.py` | 666 | `save()` has no `OSError` handling — crash on read-only filesystem |

---

## Batch 2 — Visible UX bugs

| ID | File | Line(s) | Issue |
|----|------|---------|-------|
| H7 | QML (none) | — | `plex.plexError` signal never connected in QML — auth errors silent to user |
| H8 | `WatchScreen.qml` | 609–616, 730–733 | B from show detail (entered via My List) drops user into empty show grid |
| M7 | `ListenScreen.qml` | 1318 | Progress bar `KeyNavigation.down` dead end |
| M5 | `ListenScreen.qml` | 1539 | `recentAlbumsList` missing Up-at-top → back escape |
| H4 | `WatchScreen.qml` | 205–226, 957–982 | `onMpvPlaybackReady`/`onMpvFinished` connected twice — fragile double-call |

---

## Batch 3 — Harder / higher blast radius (defer)

| ID | File | Line(s) | Issue |
|----|------|---------|-------|
| H2 | `plex_library.py` | 978–1078 | `getMovie`/`getShow`/`getSeasons`/`getEpisodes` block main thread — needs async refactor |
| H3 | `WatchScreen.qml` | 128–138 | Loading overlay stuck up to 14s on network error — needs max timeout + cancel path |
| C2 | `plex_library.py` | 1809, 1835 | `_loading_more` only reset in `except` branch — pagination can permanently stall |
| H5/M8 | `live_tv_library.py` / `WatchScreen.qml` | 207 / 224 | Shared MPV instance: Live TV loading overlay can be cleared by a Plex event |

---

## Test coverage gaps

| ID | Area | Issue |
|----|------|-------|
| T1 | `poster_cache.py` | Zero direct tests — locking, partial-file cleanup, thread-safety untested |
| T2 | `plex_timeline.py` | `stop()` thread join race untested |
| T3 | `config.py` | Malformed JSON, empty file, `save()` OSError — zero tests |
| T4 | `live_tv_library.py` | No test for guide cache staleness |
| T5 | `plex_library.py` | Zero-URL path in `playWithMpv` worker never tested (also the C1 crash path) |
| T6 | `plex_library.py` | `_artists_cache_path` hardcoded path never tested |

---

## Docs / gotchas

| ID | File | Issue |
|----|------|-------|
| G1 | `architecture.md` | Stale 8-arg `_mpvLaunchReady` signature — should be 5 args |
| G2 | `resume-project.md` | Test count will drift — update at each checkpoint |

---

## Notes

- **H1** (zero-duration track → bad LRCLIB param + silent auto-advance): partially overlaps M3 (auto-advance on bad URL). Fix M3 first; H1's LRCLIB side is low-impact.
- **M2** (server offline mid-playback): acceptable recovery path exists; no user message is the only gap. Deferred — requires a toast/notification system.
- **M4** (`_previousView` stale after playlist nav): minor cosmetic — stale header text only.
- **M6** (album list Up dead end at first item): acceptable — B is the standard back gesture.
