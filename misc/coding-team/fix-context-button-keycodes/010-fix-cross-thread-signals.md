# Task 010 — Fix cross-thread signal connections in plex_library.py

## Root cause

All signals emitted from background threads (`_executor`, `_cache_executor`,
`_poster_executor`) in `PlexLibrary.__init__` are connected with the default
`AutoConnection`. In PySide6, `AutoConnection` from a Python
`ThreadPoolExecutor` thread does NOT queue to the main thread — it behaves as
a direct connection. The slot runs on the worker thread, touching Qt model
objects from the wrong thread. The result: `librariesModelChanged` and all
other model-changed signals either silently no-op or fire on the wrong thread
where QML cannot observe them.

This is why cached data never appears on screen: `_worker_load_all_caches`
emits `_librariesReady` from `_cache_executor`, the slot runs on the worker
thread, `librariesModelChanged` is emitted from the wrong thread, and QML's
`onLibrariesModelChanged` never fires.

The signals that already have `QueuedConnection` (lines 600–618) work
correctly — those are the reference pattern.

## Objective

Add `Qt.ConnectionType.QueuedConnection` to every `.connect()` call for
signals that are emitted from background threads.

## Scope — one file: `backend/plex_library.py`

Change these lines in `__init__` (around lines 589–599):

```python
# Before
self._librariesReady.connect(self._on_libraries_ready)
self._moviesReady.connect(self._on_movies_ready)
self._showsReady.connect(self._on_shows_ready)
self._onDeckReady.connect(self._on_on_deck_ready)
self._onDeckCacheReady.connect(self._on_on_deck_cache_ready)
self._moviesCacheReady.connect(self._on_movies_cache_ready)
self._showsCacheReady.connect(self._on_shows_cache_ready)
self._availabilityReady.connect(self._on_availability_ready)
self._posterReady.connect(self._on_poster_ready)
self._machineIdentifierReady.connect(self._on_machine_identifier_ready)
self._artistsReady.connect(self._on_artists_ready)

# After
self._librariesReady.connect(self._on_libraries_ready,           Qt.ConnectionType.QueuedConnection)
self._moviesReady.connect(self._on_movies_ready,                 Qt.ConnectionType.QueuedConnection)
self._showsReady.connect(self._on_shows_ready,                   Qt.ConnectionType.QueuedConnection)
self._onDeckReady.connect(self._on_on_deck_ready,                Qt.ConnectionType.QueuedConnection)
self._onDeckCacheReady.connect(self._on_on_deck_cache_ready,     Qt.ConnectionType.QueuedConnection)
self._moviesCacheReady.connect(self._on_movies_cache_ready,      Qt.ConnectionType.QueuedConnection)
self._showsCacheReady.connect(self._on_shows_cache_ready,        Qt.ConnectionType.QueuedConnection)
self._availabilityReady.connect(self._on_availability_ready,     Qt.ConnectionType.QueuedConnection)
self._posterReady.connect(self._on_poster_ready,                 Qt.ConnectionType.QueuedConnection)
self._machineIdentifierReady.connect(self._on_machine_identifier_ready, Qt.ConnectionType.QueuedConnection)
self._artistsReady.connect(self._on_artists_ready,               Qt.ConnectionType.QueuedConnection)
```

## Non-goals / Later

- Do not change any QML files.
- Do not change any signal definitions or slot implementations.
- Do not change the already-correct connections at lines 600–618.

## Constraints / Caveats

- `Qt` is already imported in this file (`from PySide6.QtCore import Qt, ...`).
- `QueuedConnection` guarantees the slot runs on the main thread's event loop,
  regardless of which thread emits the signal. This is the correct pattern for
  all cross-thread signal/slot communication in Qt.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
  Any test that mocks these signals should be unaffected — connection type
  does not change the mock interface.
