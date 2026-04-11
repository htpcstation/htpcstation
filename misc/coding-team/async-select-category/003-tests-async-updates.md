# Task 003: Update tests for async selectCategory

## Context
With `selectCategory()` now asynchronous, tests that call `selectCategory(index)` and then immediately assert model contents will fail because the models are populated via background thread + `QueuedConnection`.

## Objective
Add a test helper that pumps the event loop until scanning completes, and update all affected tests to use it.

## Scope

### File: `tests/test_local_video_library.py`

**Add test helper** at the top of the file (after imports, before any test functions):
```python
from PySide6.QtCore import QCoreApplication
import time

def wait_for_scan(lib, timeout_ms=2000):
    """
    Pump the Qt event loop until categoryScanning becomes False.
    Allows async selectCategory worker to complete.
    
    Raises AssertionError if timeout is exceeded.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while lib.categoryScanning and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert not lib.categoryScanning, \
        f"selectCategory did not complete within {timeout_ms}ms"
```

**Find and update all tests that call `selectCategory()`** and then assert model contents:

Pattern to look for:
```python
lib.selectCategory(index)
assert lib.videosModel.rowCount() == ...
```

Change to:
```python
lib.selectCategory(index)
wait_for_scan(lib)
assert lib.videosModel.rowCount() == ...
```

**Specific tests to update**:
1. `TestSelectCategoryFlatMovies` — after each `selectCategory()` call, add `wait_for_scan(lib)`
2. `TestSelectCategoryTvShows` — same
3. `TestSelectCategoryEnrichment` — same
4. Any test that asserts `_videos.rowCount()` or `_shows.rowCount()` after calling `selectCategory()`

**Tests that may NOT need updating**:
- Tests for `selectShow()`, `selectSeason()`, `playVideo()` — these are synchronous
- Tests for scraping (`TestTmdbScraper`, `TestTmdbScraperIntegration`) — they use `time.sleep()` to wait for the scraper thread, which is fine
- Tests for enrichment helpers (`_enrich_from_cache`, `_resolve_metadata`) — if called directly without going through `selectCategory()`, they're still synchronous

## Non-goals
- Do not change the test logic/assertions — only add the wait step
- Do not add new tests for async behavior (that can be a follow-up)
- Do not touch the scraper thread tests

## Acceptance criteria
1. `wait_for_scan()` helper is defined and importable
2. All tests that were failing due to async behavior now pass
3. All 2,410 tests pass (or the same count as before, if there were pre-existing failures)
4. Test execution time does not increase by more than ~10% (the waits are usually milliseconds)
5. Timeout value (2000ms) is sufficient for all tests (no spurious failures)

## Constraints
- Use `QCoreApplication.processEvents()` to pump the event loop, not `asyncio` or other async frameworks
- Must be Qt-aware since we're testing Qt signal delivery
- The helper should use a small sleep (0.01s) to avoid busy-waiting

## Notes
If a test creates multiple library instances and multiple scans are in flight:
- The helper waits for all of them (it pumps the global event loop)
- To wait for a specific library, pass that instance to `wait_for_scan(lib)`
- Tests should be fine as-is since they typically use one `lib` instance per test function
