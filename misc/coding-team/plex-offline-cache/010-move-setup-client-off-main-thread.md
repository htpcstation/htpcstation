# Task 010 — Move _setup_client() off the main thread

## Context

`refresh()` calls `_setup_client()` synchronously on the main thread.
`_setup_client()` makes up to 4 blocking HTTP calls: `get_resources()` (10s),
`_probe_server_url()` (3s × N URLs), `switch_user()` (10s), `get_home_users()`
(10s). Worst case: 45+ seconds of UI freeze on startup and every manual refresh.

`refresh()` is called from:
- `PlexLibrary.__init__()` — app startup
- `WatchScreen.qml` — manual refresh button
- `ListenScreen.qml` — manual refresh button
- `SettingsScreen.qml` — on tab entry if music libraries empty

## Objective

Move all blocking work in `refresh()` to a worker thread. The UI must remain
responsive during server discovery, probing, and user switching.

## Approach

Combine `_setup_client()` and `_worker_refresh()` into a single worker
function that runs entirely on the executor. The main-thread `refresh()`
becomes a thin wrapper that submits the combined worker.

### New `refresh()` (main thread)

```python
@Slot()
def refresh(self) -> None:
    """Re-fetch library list and on-deck, check server availability."""
    token = self._config.plex_token
    if not token:
        self._client = None
        self._account = None
        self._server_url = ""
        self._on_availability_ready(False)
        return
    self._executor.submit(self._worker_setup_and_refresh)
```

### New `_worker_setup_and_refresh()` (worker thread)

```python
def _worker_setup_and_refresh(self) -> None:
    """Worker: set up client (server discovery, probing) then refresh data."""
    self._setup_client()  # all blocking calls now on worker thread
    if self._client is None:
        self._availabilityReady.emit(False)
        return
    # Inline the existing _worker_refresh logic
    client = self._client
    # ... rest of _worker_refresh body ...
```

Wait — `_setup_client()` modifies `self._client`, `self._server_url`,
`self._account`, etc. These are read from the main thread by `@Slot` methods
like `selectLibrary()`. This creates a race condition.

### Thread safety concern

`_setup_client()` writes to shared state (`_client`, `_server_url`, etc.)
that is read by `@Slot` methods on the main thread. Moving it to a worker
thread requires thread-safe handoff.

**Solution:** Do the network I/O on the worker thread, then marshal the
results back to the main thread via a signal, where the state is updated.

### Revised approach

1. Extract the network-heavy parts of `_setup_client()` into a worker:
   - `_resolve_server_url()` → returns URL + all URLs
   - `_probe_server_url()` → returns best working URL
   - `switch_user()` → returns token
   - `get_home_users()` → returns user list

2. The worker collects all results into a dict and emits a signal.

3. A main-thread slot receives the dict and updates `self._client`,
   `self._server_url`, etc.

### Implementation

Add a new internal signal:

```python
_setupReady = Signal("QVariant")  # dict with server_url, all_urls, user_token, etc.
```

Connect with QueuedConnection in `__init__`:

```python
self._setupReady.connect(self._on_setup_ready, Qt.ConnectionType.QueuedConnection)
```

Worker function:

```python
def _worker_setup(self) -> None:
    """Worker: resolve server URL, probe, switch user. Emits _setupReady."""
    token = self._config.plex_token
    server_id = self._config.plex_server_id

    if not server_id:
        self._setupReady.emit({"available": False, "reason": "no_server_id"})
        return

    account = PlexAccount(token)

    # Resolve server URL from plex.tv
    # (move _resolve_server_url logic here, using `account` instead of self._account)
    resources = account.get_resources()
    # ... existing resolution logic ...
    # ... probe logic ...

    # User switching
    user_token = token
    user_id = self._config.plex_user_id
    content_rating_filter = ""
    user_title = ""
    if user_id:
        # ... existing switch_user + get_home_users logic ...

    self._setupReady.emit({
        "available": True,
        "server_url": server_url,
        "all_urls": all_urls,
        "account": account,
        "user_token": user_token,
        "user_title": user_title,
        "content_rating_filter": content_rating_filter,
    })
```

Main-thread slot:

```python
def _on_setup_ready(self, result: dict) -> None:
    """Main thread: apply setup results and start data refresh."""
    if not result.get("available"):
        self._client = None
        self._on_availability_ready(False)
        return

    server_url = result["server_url"]
    self._server_url = server_url
    self._all_server_urls = result["all_urls"]
    self._account = result["account"]
    self._active_token = result["user_token"]
    # ... set other state ...

    self._client = PlexClient(server_url, token, ...)
    self._client.set_error_callback(self._on_plex_error)
    self._client.set_fallback_urls(...)

    # Now submit the data refresh
    self._executor.submit(self._worker_refresh, self._client)
```

### `__init__` startup

Replace the direct `_setup_client()` call in `__init__` with:

```python
if self._config.plex_token:
    self._executor.submit(self._worker_setup)
```

This means `_client` is `None` during initial QML setup — which is already
handled (cache-first `selectLibrary`, `_client is None` guards everywhere).

## Non-goals / Later

- Do not change `_worker_refresh` logic.
- Do not change any QML files.
- Do not change the cache-first `selectLibrary()` flow.

## Constraints / Caveats

- All shared state (`_client`, `_server_url`, `_account`, `_active_token`,
  `_content_rating_filter`, etc.) must be written ONLY on the main thread
  (in `_on_setup_ready`). The worker must not write to these fields.
- `_executor` has `max_workers=2`. The setup worker occupies one slot. If a
  `selectLibrary()` network fetch is also queued, it waits. This is fine —
  the setup must complete before network fetches can work anyway.
- The `_cache_executor` (single-thread) is unaffected — cache loads at startup
  still run immediately in parallel with the setup.
- Existing tests that mock `_setup_client()` or call `refresh()` need updating
  to handle the async pattern. The signal-based approach means tests need to
  process Qt events for the signal to be delivered.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
