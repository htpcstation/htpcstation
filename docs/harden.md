# HTPC Station — Hardening Backlog

Generated from a full codebase audit. Grouped into batches by priority.

---

## Batch 1 — Crashes and stuck UI ✅ Done

| ID | File | Issue |
|----|------|-------|
| C1 | `plex_library.py` | `_mpvLaunchReady.emit()` fixed: 8 args → 5 |
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
