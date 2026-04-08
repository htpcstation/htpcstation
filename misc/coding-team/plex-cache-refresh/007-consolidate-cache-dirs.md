# Task 007 — Consolidate all Plex cache files under plex_cache/

## Context

Currently Plex-related cache files are scattered across the config root:

```
~/.config/htpcstation/
  plex_mylist.json            ← should be in plex_cache/
  poster_cache/               ← should be plex_cache/posters/
    {sha256}.jpg
    artists_cache_{key}.json  ← should be plex_cache/artists_{key}.json
  livetv_cache/               ← should be plex_cache/guide/
    guide_cache.json
  plex_cache/                 ← already exists (from Task 006)
    state.json
    libraries_cache.json
    ondeck_cache.json
    movies_cache_{key}.json
    shows_cache_{key}.json
```

Target layout:

```
~/.config/htpcstation/
  config.json
  plex_cache/
    state.json
    libraries_cache.json
    ondeck_cache.json
    plex_mylist.json
    movies_cache_{key}.json
    shows_cache_{key}.json
    artists_cache_{key}.json
    posters/
      {sha256}.jpg
    guide/
      guide_cache.json
```

## Objective

### 1. `backend/plex_library.py`

**Module-level constants** — add/update:
```python
_PLEX_CACHE_DIR   = CONFIG_DIR / "plex_cache"          # already exists
_POSTER_CACHE_DIR = _PLEX_CACHE_DIR / "posters"        # was CONFIG_DIR / "poster_cache"
```

**`_artists_cache_path()`** — change `cache_dir` from
`CONFIG_DIR / "poster_cache"` to `_PLEX_CACHE_DIR`:
```python
def _artists_cache_path(self) -> Path:
    _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    section_key = self._current_section_key or "default"
    return _PLEX_CACHE_DIR / f"artists_cache_{section_key}.json"
```

**`plex_mylist.json` paths** — there are two references to
`CONFIG_DIR / "plex_mylist.json"` (lines ~2465 and ~2474). Change both to
`_PLEX_CACHE_DIR / "plex_mylist.json"`.

### 2. `backend/live_tv_library.py`

**Module-level constant** — change:
```python
_CACHE_DIR = CONFIG_DIR / "livetv_cache"
```
to:
```python
_PLEX_CACHE_DIR = CONFIG_DIR / "plex_cache"
_CACHE_DIR = _PLEX_CACHE_DIR / "guide"
```

No other changes needed — all uses of `_CACHE_DIR` in this file are correct.

### 3. `backend/poster_cache.py`

Read this file. The `PosterCache` class takes a `cache_dir` argument in its
constructor — the directory is passed in from `plex_library.py` at line 564:
```python
self._poster_cache = PosterCache(_POSTER_CACHE_DIR)
```

Since `_POSTER_CACHE_DIR` is now `_PLEX_CACHE_DIR / "posters"`, no change is
needed in `poster_cache.py` itself — it already uses whatever directory it's
given. Just verify this is the case.

### 4. Migration: move existing files on startup

Users who have already run the app will have files in the old locations. Add a
one-time migration function called from `PlexLibrary.__init__()` (before
`_worker_load_all_caches` is submitted):

```python
def _migrate_cache_dirs(self) -> None:
    """One-time migration: move old cache files to new plex_cache/ layout."""
    import shutil

    _PLEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # poster_cache/ → plex_cache/posters/
    old_poster_dir = CONFIG_DIR / "poster_cache"
    new_poster_dir = _PLEX_CACHE_DIR / "posters"
    if old_poster_dir.exists() and not new_poster_dir.exists():
        shutil.move(str(old_poster_dir), str(new_poster_dir))
    elif old_poster_dir.exists() and new_poster_dir.exists():
        # Both exist — move individual files, skip conflicts
        for f in old_poster_dir.iterdir():
            dest = new_poster_dir / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))
        try:
            old_poster_dir.rmdir()  # remove if now empty
        except OSError:
            pass

    # plex_mylist.json → plex_cache/plex_mylist.json
    old_mylist = CONFIG_DIR / "plex_mylist.json"
    new_mylist = _PLEX_CACHE_DIR / "plex_mylist.json"
    if old_mylist.exists() and not new_mylist.exists():
        shutil.move(str(old_mylist), str(new_mylist))

    # livetv_cache/ → plex_cache/guide/
    old_guide_dir = CONFIG_DIR / "livetv_cache"
    new_guide_dir = _PLEX_CACHE_DIR / "guide"
    if old_guide_dir.exists() and not new_guide_dir.exists():
        shutil.move(str(old_guide_dir), str(new_guide_dir))
    elif old_guide_dir.exists() and new_guide_dir.exists():
        for f in old_guide_dir.iterdir():
            dest = new_guide_dir / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))
        try:
            old_guide_dir.rmdir()
        except OSError:
            pass
```

Call it in `PlexLibrary.__init__()` before submitting `_worker_load_all_caches`:
```python
self._migrate_cache_dirs()
self._executor.submit(self._worker_load_all_caches)
```

`_migrate_cache_dirs` runs on the main thread but is fast (directory rename,
no copying unless both dirs exist). Acceptable for a one-time migration.

## Scope

- `backend/plex_library.py`
- `backend/live_tv_library.py`
- `backend/poster_cache.py` — read only, verify no changes needed

## Non-goals

- Do not change any QML files.
- Do not change `backend/config.py` — `CONFIG_DIR` stays as-is.
- Do not add a migration for the `plex_cache/` JSON files that were already
  written by Task 006 — they are already in the right place.
- Do not rename the JSON files themselves (e.g. `libraries_cache.json` stays
  as `libraries_cache.json`).

## Acceptance criteria

After this change, `~/.config/htpcstation/` contains only:
- `config.json`
- `plex_cache/` (all Plex data)

And `plex_cache/` contains:
- `state.json`, `libraries_cache.json`, `ondeck_cache.json`
- `plex_mylist.json`
- `movies_cache_{key}.json`, `shows_cache_{key}.json`, `artists_cache_{key}.json`
- `posters/` — all poster images
- `guide/` — live TV guide cache
