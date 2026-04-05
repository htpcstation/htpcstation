# Task Brief 003 — Test Coverage Gaps

## Context

Three backend modules have zero or near-zero direct test coverage for important logic.
See `docs/harden.md` section "Test coverage gaps" for the original audit findings.

## Objective

Add test files covering the three gaps. No production code changes.

## Scope

**New test files:**
- `tests/test_poster_cache.py`
- `tests/test_plex_timeline_reporter.py`
- `tests/test_config_edge_cases.py`

---

## `tests/test_poster_cache.py`

Read `backend/poster_cache.py` fully before writing tests.

Cover:
- **Happy path**: `get_poster()` returns a local file URI when the poster is already cached
- **Download**: `get_poster()` calls `client.download_image()` when not cached, writes file, returns URI
- **Partial file cleanup**: if a partial file exists (from a previous crashed download),
  it is deleted before re-downloading
- **Thread safety**: two concurrent `get_poster()` calls for the same URL do not both
  download — the lock prevents double-download (use `threading.Thread` in the test)
- **Missing thumb_path**: `get_poster()` with empty/None `thumb_path` returns `""`
- **Download failure**: if `client.download_image()` raises, `get_poster()` returns `""`
  and does not leave a partial file

---

## `tests/test_plex_timeline_reporter.py`

Read `backend/plex_timeline.py` fully before writing tests.

Cover:
- **`start()` then `stop()`**: reporter starts the background thread, `stop()` joins it
  and sends a final "stopped" report
- **`stop()` before `start()`**: no-op, does not raise
- **`update_position()`**: updates internal position; next heartbeat uses the new value
- **`update_paused()`**: updates internal paused state; next heartbeat uses "paused" state
- **Heartbeat fires**: mock the client's `report_timeline`; advance time or use a short
  interval to verify the heartbeat loop calls `report_timeline` with correct args
- **`stop()` thread join timeout**: if the thread doesn't finish within 5s, `stop()`
  returns anyway (test that `stop()` completes even if the thread is slow)

Use `unittest.mock.patch` to mock `PlexClient.report_timeline`. Do not use real network calls.

---

## `tests/test_config_edge_cases.py`

Read `backend/config.py` fully before writing tests. Use `tmp_path` (pytest fixture)
to avoid touching `~/.config/htpcstation/config.json`.

Patch `backend.config.CONFIG_FILE` and `backend.config.CONFIG_DIR` to point to
`tmp_path` locations.

Cover:
- **Missing config file**: `Config()` with no file → all defaults, no exception
- **Empty file**: `Config()` with `config.json` containing `""` → all defaults
- **Malformed JSON**: `Config()` with `config.json` containing `"not json{"` → all defaults
- **Partial config**: `Config()` with only some keys present → missing keys use defaults,
  present keys are loaded correctly
- **`save()` roundtrip**: `Config()`, set several fields, `save()`, create new `Config()`
  from same file → all fields match
- **`save()` OSError**: mock `Path.write_text` to raise `OSError` → no exception propagates
- **`set_plex_player` invalid value**: `"invalid"` → value unchanged, `save()` not called
- **`auto_skip_intro` default and persist**: defaults to `False`, `set_auto_skip_intro(True)`
  + `save()` + reload → `True`

## Constraints / Caveats

- Do not use real filesystem paths — always use `tmp_path` and patch `CONFIG_FILE`/`CONFIG_DIR`.
- `PlexTimelineReporter` uses a real background thread — use short timeouts and
  `threading.Event` to synchronise in tests rather than `time.sleep()`.
- The heartbeat interval `_HEARTBEAT_INTERVAL` may be long (10s) — patch it to a short
  value (0.05s) in tests that need the loop to fire.
