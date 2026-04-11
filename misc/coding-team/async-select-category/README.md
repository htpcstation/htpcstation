# Async selectCategory (Issue #1 / Performance Analysis)

## Problem
`LocalVideoLibrary.selectCategory()` blocks the Qt main thread for 1–2 seconds when scanning directories with 300+ video files. This causes the UI to freeze when switching video categories.

## Solution
Move filesystem scanning + cache enrichment to a `ThreadPoolExecutor` worker thread, using the same `Signal` + `QueuedConnection` pattern already established in `local_music_library.py`.

## Tasks

### [001-backend-async-executor.md](001-backend-async-executor.md)
**Implement async scanning in the backend**
- Add `ThreadPoolExecutor` to `LocalVideoLibrary`
- Refactor `selectCategory()` to kick off async work
- Add new internal signal `_workerScanFinished` with `QueuedConnection` handler
- Expose `categoryScanning` bool Property for QML
- Fix cache-dir selection bug (name-based instead of index-based)
- Wire executor shutdown in `main.py`

**Files**: `backend/local_video_library.py`, `main.py`  
**Estimated effort**: 2–3 hours

### [002-qml-spinner-and-state.md](002-qml-spinner-and-state.md)
**Update QML to show loading state and manage view transitions**
- Add `_selectedCategoryType` state property
- Remove inline view transitions from event handlers
- Add `Connections` block to transition views when scan starts
- Add spinner overlay that covers the grid while loading

**Files**: `qml/screens/LocalVideosScreen.qml`  
**Estimated effort**: 1–2 hours

### [003-tests-async-updates.md](003-tests-async-updates.md)
**Update tests to handle async selectCategory**
- Add `wait_for_scan(lib)` helper
- Update all tests that assert model contents after `selectCategory()`

**Files**: `tests/test_local_video_library.py`  
**Estimated effort**: 30 min–1 hour

## Execution order
1. **Task 001** (backend) — must complete first since QML depends on the new signals/properties
2. **Task 002** (QML) — can proceed as soon as 001 is done
3. **Task 003** (tests) — can run in parallel with 002, but 001 must be done first to avoid test failures

## Acceptance criteria
- [ ] `selectCategory()` returns immediately without blocking
- [ ] Spinner is visible while scan is in progress
- [ ] Grid/list populates when scan completes
- [ ] All 2,410 tests pass
- [ ] No regressions in navigation or other features

## Key design notes

### Backend pattern
Matches `local_music_library.py` exactly:
```
selectCategory() 
  → setScanning(True)
  → executor.submit(worker)
  → return immediately
  
worker thread:
  → scan + enrich
  → emit _workerScanFinished(items, branch)
  
main thread (via QueuedConnection):
  → resetModel(items)
  → setScanning(False)
```

### navTarget unaffected
Deep navigation (resuming from recently-played) is independent of this change. It constructs detail views directly from nav_params without relying on `selectCategory()` completing.

### Cache-dir bug fix
The old code used index (0 for Movies, 1 for TV Shows) to select cache dirs. This breaks with custom categories. The new code uses category name, which is stable:
- `cat.get("name") == "Movies"` → use `_movies_cache()`
- `cat.get("name") == "TV Shows"` → use `_tv_shows_cache()`
- Otherwise → use `_custom_category_cache(cat["name"])`

### View transition timing
The tricky part is that QML now:
1. Calls `selectCategory(index)` (returns immediately)
2. Transitions view via `Connections` callback when `categoryScanning` goes True
3. Grid/list renders empty for a moment
4. When scan completes, `videosModelChanged` signal fires, models repopulate, spinner disappears

This is correct and expected — users see a "Loading..." overlay, not an empty grid.

## Testing before checkin
1. Run full test suite: `python3 -m pytest tests/ -q`
2. Manual test on large video library:
   - Create a test library with 500+ video files
   - Switch categories
   - Verify no UI freeze
   - Verify spinner appears and disappears
3. Check that navTarget deep navigation still works (e.g., tap recently-played movie)

## References
- `backend/local_music_library.py` — AsyncPattern reference implementation
- `/home/thwonp/opencode/PERFORMANCE_ANALYSIS.md` — Full performance analysis
- `/home/thwonp/.claude/plans/nifty-napping-sphinx.md` — Architecture plan
