"""Edge-case tests for backend/config.py.

All tests use tmp_path and patch CONFIG_FILE / CONFIG_DIR so they never
touch ~/.config/htpcstation/config.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def _make_config(tmp_path: Path, content: str | None = None) -> "Config":
    """Create a Config instance backed by tmp_path."""
    from backend.config import Config

    cfg_file = tmp_path / "config.json"
    cfg_dir = tmp_path

    if content is not None:
        cfg_file.write_text(content, encoding="utf-8")

    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", cfg_dir):
        return Config()


def _save_and_reload(cfg: "Config", tmp_path: Path) -> "Config":
    """Save cfg then load a fresh Config from the same file."""
    from backend.config import Config

    cfg_file = tmp_path / "config.json"
    cfg_dir = tmp_path

    with patch("backend.config.CONFIG_FILE", cfg_file), \
         patch("backend.config.CONFIG_DIR", cfg_dir):
        cfg.save()
        return Config()


# ---------------------------------------------------------------------------
# Missing / empty / malformed file
# ---------------------------------------------------------------------------

class TestConfigLoadEdgeCases:
    def test_missing_file_uses_defaults(self, tmp_path: Path) -> None:
        """Config() with no file on disk uses all defaults without raising."""
        cfg = _make_config(tmp_path)
        assert cfg.plex_player == "mpv"
        assert cfg.auto_skip_intro is False
        assert cfg.show_retro_games_tab is True

    def test_empty_file_uses_defaults(self, tmp_path: Path) -> None:
        """Config() with an empty file uses all defaults."""
        cfg = _make_config(tmp_path, content="")
        assert cfg.plex_player == "mpv"
        assert cfg.auto_skip_intro is False

    def test_malformed_json_uses_defaults(self, tmp_path: Path) -> None:
        """Config() with malformed JSON uses all defaults without raising."""
        cfg = _make_config(tmp_path, content="not json {{{")
        assert cfg.plex_player == "mpv"
        assert cfg.auto_skip_intro is False

    def test_non_object_json_uses_defaults(self, tmp_path: Path) -> None:
        """Config() with a JSON array (not object) uses all defaults."""
        cfg = _make_config(tmp_path, content="[1, 2, 3]")
        assert cfg.plex_player == "mpv"
        assert cfg.auto_skip_intro is False

    def test_partial_config_loads_present_keys(self, tmp_path: Path) -> None:
        """Config() with only some keys present loads those and defaults the rest."""
        partial = json.dumps({"plex": {"player": "browser"}})
        cfg = _make_config(tmp_path, content=partial)
        assert cfg.plex_player == "browser"
        assert cfg.auto_skip_intro is False   # defaulted
        assert cfg.show_retro_games_tab is True  # defaulted


# ---------------------------------------------------------------------------
# Save / reload roundtrip
# ---------------------------------------------------------------------------

class TestConfigSaveRoundtrip:
    def test_save_and_reload(self, tmp_path: Path) -> None:
        """Fields set before save() are present after reloading from disk."""
        cfg = _make_config(tmp_path)
        cfg.set_plex_player("browser")
        cfg.set_auto_skip_intro(True)
        cfg.set_show_retro_games_tab(False)

        cfg2 = _save_and_reload(cfg, tmp_path)

        assert cfg2.plex_player == "browser"
        assert cfg2.auto_skip_intro is True
        assert cfg2.show_retro_games_tab is False

    def test_save_oserror_does_not_raise(self, tmp_path: Path) -> None:
        """save() swallows OSError and does not propagate."""
        cfg = _make_config(tmp_path)
        cfg_file = tmp_path / "config.json"
        cfg_dir = tmp_path

        with patch("backend.config.CONFIG_FILE", cfg_file), \
             patch("backend.config.CONFIG_DIR", cfg_dir), \
             patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            cfg.save()   # must not raise


# ---------------------------------------------------------------------------
# set_plex_player validation
# ---------------------------------------------------------------------------

class TestSetPlexPlayer:
    def test_invalid_value_ignored(self, tmp_path: Path) -> None:
        """set_plex_player() with an invalid value leaves the field unchanged."""
        cfg = _make_config(tmp_path)
        assert cfg.plex_player == "mpv"
        cfg.set_plex_player("invalid")
        assert cfg.plex_player == "mpv"

    def test_valid_values_accepted(self, tmp_path: Path) -> None:
        """set_plex_player() accepts 'mpv' and 'browser'."""
        cfg = _make_config(tmp_path)
        cfg.set_plex_player("browser")
        assert cfg.plex_player == "browser"
        cfg.set_plex_player("mpv")
        assert cfg.plex_player == "mpv"


# ---------------------------------------------------------------------------
# auto_skip_intro
# ---------------------------------------------------------------------------

class TestAutoSkipIntro:
    def test_defaults_to_false(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        assert cfg.auto_skip_intro is False

    def test_set_true_and_reload(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        cfg.set_auto_skip_intro(True)
        cfg2 = _save_and_reload(cfg, tmp_path)
        assert cfg2.auto_skip_intro is True

    def test_set_false_and_reload(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        cfg.set_auto_skip_intro(True)
        cfg.set_auto_skip_intro(False)
        cfg2 = _save_and_reload(cfg, tmp_path)
        assert cfg2.auto_skip_intro is False

    def test_coerces_to_bool(self, tmp_path: Path) -> None:
        """set_auto_skip_intro coerces truthy/falsy values to bool."""
        cfg = _make_config(tmp_path)
        cfg.set_auto_skip_intro(1)   # type: ignore[arg-type]
        assert cfg.auto_skip_intro is True
        cfg.set_auto_skip_intro(0)   # type: ignore[arg-type]
        assert cfg.auto_skip_intro is False
