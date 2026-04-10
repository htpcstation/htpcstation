# Task 002 — Fix config test isolation (real config overwrite)

## Context

`_make_config` in `tests/test_config_edge_cases.py` patches `CONFIG_FILE`/`CONFIG_DIR` only during `Config.__init__`. The `with` block exits before the Config object is returned. Any subsequent `config.set_*()` or `config.save()` call writes to the **real** `~/.config/htpcstation/config.json` because the patch is no longer active.

This wiped the user's real Plex credentials when the new tests called `set_plex_server_id("abc123", "My Server")` outside the patch context.

## Objective

Keep the `CONFIG_FILE`/`CONFIG_DIR` patches active for the entire lifetime of each test that uses `_make_config`.

## Scope

### `tests/test_config_edge_cases.py`

Replace the `_make_config` function with a `@pytest.fixture` that keeps patches active for the entire test:

```python
@pytest.fixture
def make_config(tmp_path: Path):
    """Factory fixture: returns a callable that creates a patched Config.
    
    Patches stay active for the entire test.
    """
    from backend.config import Config

    cfg_file = tmp_path / "config.json"
    cfg_dir = tmp_path

    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", cfg_dir):
        
        def _factory(content: str | None = None) -> Config:
            if content is not None:
                cfg_file.write_text(content, encoding="utf-8")
            elif not cfg_file.exists():
                pass  # let Config handle missing file
            return Config()
        
        yield _factory
```

Then update every test that calls `_make_config(tmp_path)` to use the fixture instead: replace `_make_config(tmp_path)` with `make_config()` and `_make_config(tmp_path, content=...)` with `make_config(content=...)`. Add `make_config` to each test method's parameter list.

Also update `_save_and_reload` — it can be simplified since the patches are already active from the fixture:

```python
def _save_and_reload(cfg: "Config") -> "Config":
    from backend.config import Config
    cfg.save()
    return Config()
```

Update its call sites to drop the `tmp_path` argument.

## Non-goals

- Do NOT change any test assertions or test logic — only the fixture wiring.
- Do NOT touch other test files. `test_settings_manager.py` mocks `config.save`, so it doesn't have this problem.

## Constraints

- All tests must pass (`python3 -m pytest tests/test_config_edge_cases.py -q`).
- Verify the real config is NOT touched by running: `stat ~/.config/htpcstation/config.json` before and after the test run — mtime must not change.
