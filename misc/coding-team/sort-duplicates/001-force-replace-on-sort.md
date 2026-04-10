# Task 001 — Force model replace on sort/filter to prevent duplicates

## Context

When `sortMovies()` fires, it locally sorts the model (500 items), resets `_movies_loaded = 0`, and submits a network fetch. When the first page (50 items) arrives in `_on_movies_ready`, the size guard `len(movies) >= len(model)` → `50 >= 500` → false → `set_movies` is skipped. But `_movies_loaded` increments to 50. When the next page arrives, `_movies_loaded != 0` → append branch → duplicates.

The size guard was added to prevent scroll jumps on lazy-refresh re-entry (returning from detail view). It should NOT apply when the user explicitly requests a sort or filter change.

Same issue exists for shows via `sortShows`/`filterShowsByGenre`/`_on_shows_ready`.

## Objective

Ensure sort/filter re-fetches always replace the model on first page, bypassing the size guard.

## Scope

### `backend/plex_library.py`

1. Add two flags in `__init__`:
   ```python
   self._movies_force_replace: bool = False
   self._shows_force_replace: bool = False
   ```

2. Set `self._movies_force_replace = True` in:
   - `sortMovies()` (around line 989, before the network submit)
   - `filterByGenre()` (around line 1009, before the network submit)

3. Set `self._shows_force_replace = True` in:
   - `sortShows()` (same pattern)
   - `filterShowsByGenre()` (same pattern)

4. In `_on_movies_ready`, change the first-page branch:
   ```python
   if self._movies_loaded == 0:
       if self._movies_force_replace or len(movies) >= len(self._movies_model._movies):
           self._movies_model.set_movies(movies)
           self.moviesModelChanged.emit()
       self._movies_force_replace = False
       ...
   ```

5. In `_on_shows_ready`, same change with `_shows_force_replace`.

## Non-goals

- Do NOT change the artist path — artists aren't paginated and use a `>` guard (fixed earlier).
- Do NOT change QML files.
- Do NOT change `selectLibrary()` — the lazy-refresh path should NOT set force_replace.

## Tests

Add tests in `tests/test_plex_backend.py` (or a new file if cleaner):

1. `test_sort_movies_forces_model_replace` — pre-populate model with 500 items, call `sortMovies`, simulate first-page response with 50 items → `set_movies` IS called (model replaced).
2. `test_lazy_refresh_skips_replace` — pre-populate model with 500 items, simulate first-page response with 50 items WITHOUT force flag → `set_movies` is NOT called (existing guard behavior preserved).
3. Same two tests for shows.

## Acceptance criteria

- Sorting movies/shows multiple times does not produce duplicates.
- Returning from detail view still preserves scroll position (size guard still works for lazy refresh).
- All tests pass.
