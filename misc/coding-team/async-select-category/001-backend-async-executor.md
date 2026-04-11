# Task 001: Backend async executor and signals

## Context
`LocalVideoLibrary.selectCategory()` currently blocks the main thread scanning the filesystem and loading JSON caches. This task adds a `ThreadPoolExecutor` worker pattern matching `local_music_library.py` to make the scan async.

## Objective
Refactor `LocalVideoLibrary` to kick off category scanning on a background thread, marshal results back to main thread via `QueuedConnection`, and expose a `categoryScanning` bool Property for QML loading state.

## Scope

### File: `backend/local_video_library.py`

**In `LocalVideoLibrary.__init__`** (after line 976):
1. Add import: `from concurrent.futures import ThreadPoolExecutor`
2. Add `self._executor = ThreadPoolExecutor(max_workers=1)`
3. Add `self._category_scanning = False`
4. Add internal signal: `self._workerScanFinished = Signal(object, str)` — `(items, branch: "flat"|"tv_shows")`
5. Connect: `self._workerScanFinished.connect(self._on_worker_scan_finished, Qt.ConnectionType.QueuedConnection)`

**Add new public signal and property** (alongside existing `videosModelChanged`, etc.):
```python
categoryScanningChanged = Signal()

def _get_category_scanning(self) -> bool:
    return self._category_scanning

categoryScanning = Property(
    bool,
    fget=_get_category_scanning,
    notify=categoryScanningChanged,
)
```

**Rewrite `selectCategory()` method** (lines 1052–1087):
- Store `self._current_category_index = index` first
- Reset sort/filter state
- Set `self._category_scanning = True`, emit `categoryScanningChanged`
- Emit `currentCategoryIndexChanged` (so QML can read the index immediately)
- Get the category dict: `cat = cats[index]`
- Determine branch: `branch = "flat" if cat["type"] == "flat" else "tv_shows"`
- Submit worker: `self._executor.submit(self._worker_scan_category, cat, branch)`
- Return immediately (no model updates)

**Add new worker method** `_worker_scan_category(self, cat: dict, branch: str)`:
```python
def _worker_scan_category(self, cat: dict, branch: str) -> None:
    """Scan a category asynchronously on an executor thread."""
    try:
        if branch == "flat":
            items = _scan_flat(cat["paths"])
            # ← FIX: use name-based cache dir, not index-based
            cache = _movies_cache() if cat.get("name") == "Movies" else _custom_category_cache(cat["name"])
        else:
            items = _scan_tv_shows(cat["paths"])
            # ← FIX: use name-based cache dir, not index-based
            cache = _tv_shows_cache() if cat.get("name") == "TV Shows" else _custom_category_cache(cat["name"])
        _enrich_from_cache(items, cache)
    except Exception:
        logger.exception("_worker_scan_category: unexpected error")
        items = []
    self._workerScanFinished.emit(items, branch)
```

**Add new main-thread handler** `_on_worker_scan_finished(self, items: list, branch: str)`:
```python
@Slot(object, str)
def _on_worker_scan_finished(self, items: list, branch: str) -> None:
    """Receive scan results from worker thread and update models."""
    if branch == "flat":
        self._reset_model(self._videos, items)
        self._reset_model(self._shows, [])
        self._reset_model(self._seasons, [])
        self._reset_model(self._episodes, [])
        self.videosModelChanged.emit()
    else:
        self._reset_model(self._shows, items)
        self._reset_model(self._videos, [])
        self._reset_model(self._seasons, [])
        self._reset_model(self._episodes, [])
        self.showsModelChanged.emit()

    self._category_scanning = False
    self.categoryScanningChanged.emit()
```

**Add shutdown slot** (at end of class, before any subclass markers):
```python
@Slot()
def shutdown(self) -> None:
    """Shutdown the executor. Called on app quit."""
    self._executor.shutdown(wait=False)
```

### File: `main.py`

**After `local_videos` is instantiated** (around line 145), add:
```python
app.aboutToQuit.connect(local_videos.shutdown)
```

## Non-goals
- Do not change `_enrich_from_cache`, `_scan_flat`, `_scan_tv_shows`, `_reset_model` — they work as-is on the worker
- Do not add per-item progress callbacks
- Do not change `rescanCategory` — it delegates to the new async `selectCategory` for free

## Acceptance criteria
1. `selectCategory(index)` returns immediately without blocking
2. `_category_scanning` goes True, then False as the worker runs
3. Model population happens via `_on_worker_scan_finished` (not inline in `selectCategory`)
4. The name-based cache-dir fix prevents custom categories from using the wrong cache
5. `app.aboutToQuit` triggers executor shutdown
6. No test breakage from backend changes alone (tests will need updates in Task 003)

## Constraints
- No changes to the scraper thread's `_start_scrape` or `_emit_scrape_finished` — they already call `selectCategory` correctly and will benefit from it becoming async
- The internal signal must use `QueuedConnection` to safely cross thread boundaries
