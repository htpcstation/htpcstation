# Task 004 — Probe server URL on setup, fallback to remote connections

## Context

`_setup_client()` picks the highest-priority server URL (local first) from
plex.tv resources and creates `PlexClient` with it. On an external network,
the local URL (e.g. `http://192.168.0.2:32400`) is unreachable. All requests
fail after ~4s of retries. The existing `try_next_connection()` fallback
mechanism updates `_server_url` for future requests, but the failed request
is already done and nothing retries it. The app is stuck showing cached data
— movie details, albums, and all network-dependent features are broken.

## Objective

Before creating the `PlexClient`, probe the selected URL. If unreachable,
try the next URL from `_all_server_urls` in priority order. The client starts
with a verified working URL from the beginning. This keeps local preference
(local URLs respond instantly when reachable) but transparently falls through
to remote/relay connections when on an external network.

## Scope — one file: `backend/plex_library.py`

### 1. Add `_probe_server_url()` helper

```python
def _probe_server_url(self, url: str, timeout: float = 3.0) -> bool:
    """Quick probe: is the server reachable at this URL?

    Uses a lightweight GET /identity with a short timeout.
    Returns True if the server responds with status < 400.
    """
    try:
        import requests
        response = requests.get(
            f"{url}/identity",
            headers=self._identity_headers(),
            timeout=timeout,
        )
        return response.status_code < 400
    except Exception:
        return False
```

Check if `_identity_headers()` exists or if headers need to be constructed
differently. The probe just needs the Plex identity headers (same ones
`PlexClient` uses). If `PlexClient` is not yet created at probe time, build
a minimal set: `X-Plex-Client-Identifier`, `X-Plex-Product`, `X-Plex-Version`.
Actually, the `/identity` endpoint doesn't require auth headers at all — it
returns the server's machine identifier. A plain `requests.get(url, timeout=t)`
should work. Check `PlexClient.get_identity()` to confirm.

Use a short timeout: 3s is enough to detect a reachable local server (responds
in <100ms) and fail fast on unreachable IPs. Connection refused is instant.
The 3s covers the case where the IP exists but the port is closed (TCP timeout).

### 2. Modify `_setup_client()` — probe before creating client

After `_resolve_server_url()` succeeds and `_all_server_urls` is populated,
probe the best URL. If it fails, iterate through the rest:

```python
server_url = self._resolve_server_url()
if server_url:
    # Cache for offline startup
    if server_url != self._config.plex_server_url:
        self._config.set_plex_server_url(server_url)

    # Probe the best URL; fall through to alternatives if unreachable
    if not self._probe_server_url(server_url):
        logger.info(
            "PlexLibrary: primary URL %s unreachable, trying alternatives", server_url
        )
        found = False
        for alt_url in self._all_server_urls:
            if alt_url == server_url:
                continue
            if self._probe_server_url(alt_url):
                logger.info("PlexLibrary: using alternative URL %s", alt_url)
                server_url = alt_url
                found = True
                break
        if not found:
            logger.warning("PlexLibrary: all server URLs unreachable")
            # Fall through — create client with best URL anyway so the
            # existing retry/fallback mechanism can still try later.
            # The cached URL from config is still set from above.
```

Note: even if all probes fail, still create the client with the original best
URL. The existing retry + `try_next_connection()` mechanism is the safety net.
The probe is an optimisation, not a hard gate.

### 3. Probe timeout tuning

Use 3s timeout for the probe. On local network, the server responds in <100ms
so no added latency. On external network with unreachable local IP:
- Connection refused: instant (<10ms)
- TCP timeout (IP not routable): up to 3s per probe

Worst case: local URL times out (3s) + one remote URL probe (~500ms) = ~3.5s
added to startup. This is acceptable since the alternative is the app being
non-functional on external networks.

### 4. Don't cache a remote URL as the primary

The cached `plex_server_url` in config should remain the local URL. When on
an external network, the probe picks a remote URL for this session, but the
config keeps the local URL so the next launch on the home network uses it
directly.

Change the cache-on-success logic:
```python
if server_url:
    # Only cache local URLs — remote/relay URLs are session-specific
    best_url = self._all_server_urls[0] if self._all_server_urls else server_url
    if best_url != self._config.plex_server_url:
        self._config.set_plex_server_url(best_url)
```

This way the config always stores the highest-priority (local) URL, not
whatever URL happened to work this session.

## Non-goals / Later

- Do not change `PlexClient._get()` retry logic or `try_next_connection()`.
- Do not change `_resolve_server_url()` — it already sorts and stores all URLs.
- Do not change any QML files.
- Do not change the cache-first `selectLibrary()` logic.

## Constraints / Caveats

- `_setup_client()` runs on the main thread (called from `refresh()` which is
  a `@Slot`). The probe blocks the main thread for up to 3s per URL. This is
  acceptable because `refresh()` already calls `_resolve_server_url()` which
  makes a blocking HTTP call to plex.tv on the main thread. The probe adds
  at most one more blocking call in the common case (local URL works or fails
  fast). If this becomes a problem, `refresh()` should be moved to a worker
  thread entirely — but that's a larger refactor.
- The `/identity` endpoint does not require authentication. It returns the
  server's machine identifier. Verify this by checking `PlexClient.get_identity()`.
- `requests` is already imported in `plex_library.py` — check before adding.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
