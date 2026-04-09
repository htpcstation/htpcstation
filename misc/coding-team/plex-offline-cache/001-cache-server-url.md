# Task 001 — Cache server URL in config.json

## Context

`PlexLibrary._setup_client()` calls `_resolve_server_url()` which hits
`plex.tv/api/v2/resources` to discover the server URL every time. When
the internet is down, this fails and `_client` is set to `None`. With no
client, `selectLibrary()`, `refresh()`, and all network-dependent code
paths bail out immediately — the app cannot load any Plex data, even
from local cache.

The Plex server is typically on the local network (e.g. `http://192.168.0.2:32400`).
It's reachable even without internet. But the URL is never persisted — it's
re-resolved from plex.tv on every app launch.

## Objective

Persist the last-known server URL in `config.json` so `_setup_client()` can
create a working `PlexClient` when plex.tv is unreachable.

## Scope

### `backend/config.py`

1. Add `_plex_server_url: str = ""` field in `__init__` (alongside `_plex_server_id`).

2. Add property + setter:
   ```python
   @property
   def plex_server_url(self) -> str:
       return self._plex_server_url

   def set_plex_server_url(self, url: str) -> None:
       self._plex_server_url = url.strip()
       self.save()
   ```

3. In `save()`, add to the `"plex"` dict:
   ```python
   "server_url": self._plex_server_url,
   ```

4. In `_load()`, inside the `plex` block:
   ```python
   self._plex_server_url = plex.get("server_url", "")
   ```

### `backend/plex_library.py` — `_setup_client()`

After successful `_resolve_server_url()` (line ~2909), persist the URL:
```python
server_url = self._resolve_server_url()
if server_url:
    # Cache for offline startup
    if server_url != self._config.plex_server_url:
        self._config.set_plex_server_url(server_url)
```

When `_resolve_server_url()` returns `None`, fall back to the cached URL:
```python
if not server_url:
    server_url = self._config.plex_server_url
    if server_url:
        logger.info("PlexLibrary: plex.tv unreachable, using cached server URL: %s", server_url)
    else:
        self._client = None
        self._server_url = ""
        logger.info("PlexLibrary: could not resolve server URL and no cached URL available")
        return
```

Also populate `self._all_server_urls` from the cached URL when using the
fallback (it will be a single-element list, but that's fine — it prevents
`_client.set_fallback_urls([])` from being empty):
```python
if not self._all_server_urls:
    self._all_server_urls = [server_url]
```

### `backend/plex_library.py` — `_resolve_server_url()`

The `get_resources()` call can raise on network failure. Wrap it:
```python
try:
    resources = self._account.get_resources()
except Exception as exc:
    logger.warning("PlexLibrary: failed to fetch resources from plex.tv: %s", exc)
    return None
```

Check if `get_resources()` already handles this — if it catches exceptions
internally and returns `[]`, the existing `next(..., None)` handles it.
If it lets exceptions propagate, add the try/except.

## Non-goals / Later

- Do not cache multiple server URLs or the full connection list — just the
  single best URL.
- Do not change user token caching — that's a separate concern.
- Do not change `selectLibrary()` — that's Task 002.

## Constraints / Caveats

- The cached URL may go stale (e.g. DHCP reassignment). This is acceptable —
  `PlexClient` already has `try_next_connection()` fallback logic, and the
  URL will be refreshed on the next successful plex.tv resolution.
- The `Config.save()` wipe guard (refuses to write if token+server_id are
  blank but on-disk file has them) should not be affected — `server_url` is
  a new field that doesn't participate in the guard.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
