# Task 001 — Skip artist model reset when network returns same count

## Context

When navigating back from artist detail to the artist grid, `onCurrentViewChanged` in `ListenScreen.qml:348-350` calls `plex.selectLibrary()` as a "lazy refresh". This skips cache reload (model already has content — line 919 guard), but still submits a network fetch via `_worker_load_section` (line 937).

~1 second later the network response arrives → `_on_artists_ready` → `set_artists()` → `beginResetModel()`/`endResetModel()` → GridView scroll position and focus state reset.

Movies/shows don't have this problem because they're paginated: the first network page (50 items) is smaller than the cached model (500+), so the `len(movies) >= len(model)` guard in `_on_movies_ready` (line 2260) skips `set_movies()`. Artists aren't paginated — the full set comes in one response, so `len(artists) >= len(model)` is always true.

## Objective

Prevent `_on_artists_ready` from calling `set_artists()` (and thus `beginResetModel()`) when the model already has content and the incoming network data has the same count.

## Scope

**`backend/plex_library.py`, line 2346 only.**

Change the guard from `>=` to `>`:

```python
# Before
if len(artists) >= len(self._artists_model._artists):

# After
if len(artists) > len(self._artists_model._artists):
```

This means:
- Initial load (model empty, incoming > 0): replaces ✓
- Network response after cache with same count: skips ✓ (no jump)
- Server genuinely has MORE artists than cached: replaces ✓
- Server has fewer artists (already handled — current code also skips): skips ✓

The rest of `_on_artists_ready` still runs: cache merge and poster downloads proceed normally.

## Non-goals

- Do NOT change the `onCurrentViewChanged` handler in ListenScreen.qml — the lazy refresh pattern is intentional for background data freshness.
- Do NOT add index/focus save-restore logic in QML.
- Do NOT change `_on_movies_ready` or `_on_shows_ready`.

## Constraints

- The existing test `test_on_artists_ready_skips_when_smaller` verifies the "incoming smaller than model" case. Add a companion test: when incoming count equals existing count, `set_artists` should NOT be called (i.e., `beginResetModel` should not fire). Name it `test_on_artists_ready_skips_when_same_count`.

## Acceptance criteria

- `>=` changed to `>` on line 2346.
- New test `test_on_artists_ready_skips_when_same_count` passes.
- All existing tests pass (`python3 -m pytest tests/ -q`).
