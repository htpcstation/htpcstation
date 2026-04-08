# Task 001 — Fix test isolation, cache pollution, and suite speed

## Problems

### 1. Cache pollution (critical)
`_make_lib()` patches `backend.config.CONFIG_DIR` but NOT the module-level
constants `backend.plex_library._PLEX_CACHE_DIR` and
`backend.plex_library._POSTER_CACHE_DIR`. These are computed at import time:
```python
_PLEX_CACHE_DIR   = CONFIG_DIR / "plex_cache"
_POSTER_CACHE_DIR = _PLEX_CACHE_DIR / "posters"
```
Patching `CONFIG_DIR` after import has no effect. So every `PlexLibrary()`
instantiation in tests writes to the real `~/.config/htpcstation/plex_cache/`:
- `_migrate_cache_dirs()` moves real user files
- `_save_sort_state()` overwrites real `state.json`
- `_worker_load_all_caches` reads/writes real cache files

This causes:
- Test failures when real state.json has values that contradict test expectations
- Real user cache files being corrupted or overwritten by tests

### 2. Rate limiting / slow instantiation
Every `PlexLibrary()` instantiation:
- Calls `_migrate_cache_dirs()` (filesystem ops on real paths)
- Submits `_worker_load_all_caches` to `_cache_executor` (disk I/O on real paths)
- Creates two `ThreadPoolExecutor` instances (`_executor`, `_poster_executor`,
  `_cache_executor`) that are never shut down between tests

With hundreds of test instantiations, thread pool creation and disk I/O accumulate.

### 3. Test suite speed
48s for ~2027 tests. Primary costs:
- Thread pool creation per `PlexLibrary` instantiation
- Disk I/O from unpatched cache paths
- `_migrate_cache_dirs()` running on every instantiation

## Fix

### A. Add `conftest.py` with autouse fixtures

Create `tests/conftest.py` (or add to existing if present) with:

```python
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def isolate_plex_cache(tmp_path: Path, monkeypatch):
    """Redirect all Plex cache I/O to tmp_path for every test.

    Patches the module-level constants that are computed at import time,
    so tests never touch ~/.config/htpcstation/plex_cache/.
    """
    plex_cache = tmp_path / "plex_cache"
    posters = plex_cache / "posters"
    plex_cache.mkdir(parents=True, exist_ok=True)
    posters.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("backend.plex_library._PLEX_CACHE_DIR", plex_cache)
    monkeypatch.setattr("backend.plex_library._POSTER_CACHE_DIR", posters)
    monkeypatch.setattr("backend.live_tv_library._CACHE_DIR", plex_cache / "guide")
```

### B. Patch `_migrate_cache_dirs` and `_cache_executor` in `_make_lib` helpers

The two most expensive operations in `PlexLibrary.__init__` for tests are:
1. `_migrate_cache_dirs()` — filesystem ops, should be a no-op in tests
2. `_cache_executor.submit(_worker_load_all_caches)` — disk I/O, should be
   a no-op in tests (cache state is controlled per-test via tmp_path)

Update ALL `_make_lib()` / `_make_lib_with_tmp()` helpers across all test files
to also patch these:

```python
with patch("backend.plex_library.PlexClient"), \
     patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
     patch("backend.config.CONFIG_FILE"), \
     patch("backend.config.CONFIG_DIR"), \
     patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"), \
     patch("backend.plex_library._POSTER_CACHE_DIR", tmp_path / "plex_cache" / "posters"):
    config = MagicMock(spec=Config)
    ...
    lib = PlexLibrary(config)
    lib._migrate_cache_dirs = lambda: None   # no-op after construction
    lib._cache_executor.submit = lambda fn, *args, **kwargs: None  # no-op
```

Wait — `_migrate_cache_dirs` and `_cache_executor.submit` are called during
`__init__`, so patching after construction is too late. Instead, patch them
before construction:

```python
with patch("backend.plex_library.PlexClient"), \
     patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
     patch("backend.config.CONFIG_FILE"), \
     patch("backend.config.CONFIG_DIR"), \
     patch("backend.plex_library._PLEX_CACHE_DIR", tmp_path / "plex_cache"), \
     patch("backend.plex_library._POSTER_CACHE_DIR", tmp_path / "plex_cache" / "posters"), \
     patch.object(PlexLibrary, "_migrate_cache_dirs", lambda self: None):
    config = MagicMock(spec=Config)
    ...
    lib = PlexLibrary(config)
    # Drain any submitted cache worker (it ran against tmp_path, harmless)
```

For `_cache_executor.submit`, the autouse fixture redirecting `_PLEX_CACHE_DIR`
to `tmp_path` means the cache worker reads from tmp_path (empty), finds nothing,
and exits immediately. This is acceptable — no need to patch it out entirely.

### C. Fix `_make_lib_with_tmp` to patch `_PLEX_CACHE_DIR`

The existing `_make_lib_with_tmp` in `test_plex_backend.py` patches
`backend.plex_library.CONFIG_DIR` but not `_PLEX_CACHE_DIR`. Fix it:

```python
def _make_lib_with_tmp(tmp_path):
    from backend.plex_library import PlexLibrary
    from backend.config import Config

    plex_cache = tmp_path / "plex_cache"
    plex_cache.mkdir(parents=True, exist_ok=True)

    with patch("backend.plex_library.PlexClient"), \
         patch("backend.plex_library.PlexAccount", _make_plex_account_mock()), \
         patch("backend.config.CONFIG_FILE"), \
         patch("backend.config.CONFIG_DIR", tmp_path), \
         patch("backend.plex_library.CONFIG_DIR", tmp_path), \
         patch("backend.plex_library._PLEX_CACHE_DIR", plex_cache), \
         patch("backend.plex_library._POSTER_CACHE_DIR", plex_cache / "posters"), \
         patch.object(PlexLibrary, "_migrate_cache_dirs", lambda self: None):
        config = MagicMock(spec=Config)
        config.plex_server_id = "server123"
        config.plex_token = "tok"
        config.plex_user_id = None
        lib = PlexLibrary(config)
    return lib
```

### D. Fix `test_plex_music.py` direct CONFIG_DIR mutation

Lines ~1490–1654 in `test_plex_music.py` directly assign:
```python
plex_lib_module.CONFIG_DIR = config_module.CONFIG_DIR
_plm._PLEX_CACHE_DIR = config_module.CONFIG_DIR / "plex_cache"
```
This mutates the real module globals. Replace with `monkeypatch` or `patch`
using `tmp_path` instead of `config_module.CONFIG_DIR`.

Read those test methods fully before rewriting them.

### E. Fix the 3 currently failing tests

After the isolation fixes, re-run the suite. The 3 failures
(`TestSortMovies::test_sort_rating_maps_to_correct_api_param`,
`TestSortMovies::test_sort_year_desc_maps_to_correct_api_param`,
`TestFilterByGenre::test_filter_empty_string_clears_genre`) should be fixed
by the isolation — they fail because `_save_sort_state` writes to real
`state.json` which then pollutes subsequent tests. Verify they pass after
the isolation fix.

## Scope

- `tests/conftest.py` — create or update
- `tests/test_plex_backend.py` — update `_make_lib_with_tmp` and all
  class-level `_make_lib` methods
- `tests/test_plex_music.py` — fix direct CONFIG_DIR mutation
- `tests/test_harden_batch1.py` — check and fix if needed
- Any other test file that instantiates `PlexLibrary` without proper isolation

## Non-goals

- Do not change any production code.
- Do not delete or rewrite test logic — only fix isolation.
- Do not add new tests.

## Acceptance criteria

- `pytest tests/` passes with 0 failures, deterministically (run 3 times)
- No files written to `~/.config/htpcstation/` during test run
- Suite completes in under 35s (target: reduce from 48s)
