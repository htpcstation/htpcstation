"""Edge-case tests for backend/config.py.

All tests use tmp_path and patch CONFIG_FILE / CONFIG_DIR so they never
touch ~/.config/htpcstation/config.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


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


def _save_and_reload(cfg: "Config") -> "Config":
    """Save cfg then load a fresh Config from the same file."""
    from backend.config import Config

    cfg.save()
    return Config()


# ---------------------------------------------------------------------------
# Missing / empty / malformed file
# ---------------------------------------------------------------------------

class TestConfigLoadEdgeCases:
    def test_missing_file_uses_defaults(self, make_config) -> None:
        """Config() with no file on disk uses all defaults without raising."""
        cfg = make_config()
        assert cfg.plex_player == "mpv"
        assert cfg.auto_skip_intro is False
        assert cfg.show_retro_games_tab is True

    def test_empty_file_uses_defaults(self, make_config) -> None:
        """Config() with an empty file uses all defaults."""
        cfg = make_config(content="")
        assert cfg.plex_player == "mpv"
        assert cfg.auto_skip_intro is False

    def test_malformed_json_uses_defaults(self, make_config) -> None:
        """Config() with malformed JSON uses all defaults without raising."""
        cfg = make_config(content="not json {{{")
        assert cfg.plex_player == "mpv"
        assert cfg.auto_skip_intro is False

    def test_non_object_json_uses_defaults(self, make_config) -> None:
        """Config() with a JSON array (not object) uses all defaults."""
        cfg = make_config(content="[1, 2, 3]")
        assert cfg.plex_player == "mpv"
        assert cfg.auto_skip_intro is False

    def test_partial_config_loads_present_keys(self, make_config) -> None:
        """Config() with only some keys present loads those and defaults the rest."""
        partial = json.dumps({"plex": {"player": "browser"}})
        cfg = make_config(content=partial)
        assert cfg.plex_player == "browser"
        assert cfg.auto_skip_intro is False   # defaulted
        assert cfg.show_retro_games_tab is True  # defaulted


# ---------------------------------------------------------------------------
# Save / reload roundtrip
# ---------------------------------------------------------------------------

class TestConfigSaveRoundtrip:
    def test_save_and_reload(self, make_config) -> None:
        """Fields set before save() are present after reloading from disk."""
        cfg = make_config()
        cfg.set_plex_player("browser")
        cfg.set_auto_skip_intro(True)
        cfg.set_show_retro_games_tab(False)

        cfg2 = _save_and_reload(cfg)

        assert cfg2.plex_player == "browser"
        assert cfg2.auto_skip_intro is True
        assert cfg2.show_retro_games_tab is False

    def test_save_oserror_does_not_raise(self, make_config, tmp_path: Path) -> None:
        """save() swallows OSError and does not propagate."""
        cfg = make_config()

        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            cfg.save()   # must not raise


# ---------------------------------------------------------------------------
# set_plex_player validation
# ---------------------------------------------------------------------------

class TestSetPlexPlayer:
    def test_invalid_value_ignored(self, make_config) -> None:
        """set_plex_player() with an invalid value leaves the field unchanged."""
        cfg = make_config()
        assert cfg.plex_player == "mpv"
        cfg.set_plex_player("invalid")
        assert cfg.plex_player == "mpv"

    def test_valid_values_accepted(self, make_config) -> None:
        """set_plex_player() accepts 'mpv' and 'browser'."""
        cfg = make_config()
        cfg.set_plex_player("browser")
        assert cfg.plex_player == "browser"
        cfg.set_plex_player("mpv")
        assert cfg.plex_player == "mpv"


# ---------------------------------------------------------------------------
# auto_skip_intro
# ---------------------------------------------------------------------------

class TestAutoSkipIntro:
    def test_defaults_to_false(self, make_config) -> None:
        cfg = make_config()
        assert cfg.auto_skip_intro is False

    def test_set_true_and_reload(self, make_config) -> None:
        cfg = make_config()
        cfg.set_auto_skip_intro(True)
        cfg2 = _save_and_reload(cfg)
        assert cfg2.auto_skip_intro is True

    def test_set_false_and_reload(self, make_config) -> None:
        cfg = make_config()
        cfg.set_auto_skip_intro(True)
        cfg.set_auto_skip_intro(False)
        cfg2 = _save_and_reload(cfg)
        assert cfg2.auto_skip_intro is False

    def test_coerces_to_bool(self, make_config) -> None:
        """set_auto_skip_intro coerces truthy/falsy values to bool."""
        cfg = make_config()
        cfg.set_auto_skip_intro(1)   # type: ignore[arg-type]
        assert cfg.auto_skip_intro is True
        cfg.set_auto_skip_intro(0)   # type: ignore[arg-type]
        assert cfg.auto_skip_intro is False


# ---------------------------------------------------------------------------
# Plex server name / user title caching
# ---------------------------------------------------------------------------

class TestPlexServerNameUserTitle:
    def test_defaults_empty(self, make_config) -> None:
        """New config has empty server_name and user_title."""
        cfg = make_config()
        assert cfg.plex_server_name == ""
        assert cfg.plex_user_title == ""

    def test_set_server_id_stores_name(self, make_config) -> None:
        """set_plex_server_id stores both server_id and server_name."""
        cfg = make_config()
        cfg.set_plex_server_id("abc123", "My Server")
        assert cfg.plex_server_id == "abc123"
        assert cfg.plex_server_name == "My Server"

    def test_set_user_id_stores_title(self, make_config) -> None:
        """set_plex_user_id stores both user_id and user_title."""
        cfg = make_config()
        cfg.set_plex_user_id(42, "Alice")
        assert cfg.plex_user_id == 42
        assert cfg.plex_user_title == "Alice"

    def test_server_name_persists_through_save_reload(self, make_config) -> None:
        """server_name survives a save/reload cycle."""
        cfg = make_config()
        cfg.set_plex_server_id("srv1", "Living Room")
        cfg2 = _save_and_reload(cfg)
        assert cfg2.plex_server_name == "Living Room"
        assert cfg2.plex_server_id == "srv1"

    def test_user_title_persists_through_save_reload(self, make_config) -> None:
        """user_title survives a save/reload cycle."""
        cfg = make_config()
        cfg.set_plex_user_id(7, "Bob")
        cfg2 = _save_and_reload(cfg)
        assert cfg2.plex_user_title == "Bob"
        assert cfg2.plex_user_id == 7

    def test_clear_server_clears_name(self, make_config) -> None:
        """Setting server_id to empty clears server_name too."""
        cfg = make_config()
        cfg.set_plex_server_id("srv1", "My Server")
        cfg.set_plex_server_id("", "")
        assert cfg.plex_server_id is None
        assert cfg.plex_server_name == ""

    def test_old_config_without_names_loads_empty(self, make_config) -> None:
        """Config files from before this change (no server_name/user_title) load fine."""
        old_data = {"plex": {"token": "tok", "server_id": "s1", "user_id": 5}}
        cfg = make_config(content=json.dumps(old_data))
        assert cfg.plex_server_id == "s1"
        assert cfg.plex_server_name == ""
        assert cfg.plex_user_id == 5
        assert cfg.plex_user_title == ""
