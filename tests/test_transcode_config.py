"""Tests for plex_transcode_mode and hw_decode_codecs config properties."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import Config


def _make_config(tmp_path: Path, data: dict | None = None) -> Config:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(data or {}), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        return Config()


class TestPlexTranscodeMode:
    def test_default_is_auto(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.plex_transcode_mode == "auto"

    @pytest.mark.parametrize("mode", ["direct", "auto", "480p", "720p", "1080p"])
    def test_set_valid_modes(self, tmp_path: Path, mode: str) -> None:
        config = _make_config(tmp_path)
        config.set_plex_transcode_mode(mode)
        assert config.plex_transcode_mode == mode

    def test_set_invalid_mode_ignored(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.set_plex_transcode_mode("4k")
        assert config.plex_transcode_mode == "auto"

    def test_persists_to_disk(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_plex_transcode_mode("720p")

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["transcode_mode"] == "720p"

    def test_round_trip(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_plex_transcode_mode("1080p")

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()
        assert config2.plex_transcode_mode == "1080p"

    def test_load_invalid_value_uses_default(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, {"plex": {"transcode_mode": "banana"}})
        assert config.plex_transcode_mode == "auto"


class TestHwDecodeCodecs:
    def test_default_is_empty(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert config.hw_decode_codecs == []

    def test_set_and_get(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.set_hw_decode_codecs(["hevc", "h264", "vp9"])
        assert config.hw_decode_codecs == ["h264", "hevc", "vp9"]  # sorted

    def test_deduplicates(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.set_hw_decode_codecs(["h264", "h264", "hevc"])
        assert config.hw_decode_codecs == ["h264", "hevc"]

    def test_getter_returns_copy(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.set_hw_decode_codecs(["h264"])
        result = config.hw_decode_codecs
        result.append("hevc")
        assert config.hw_decode_codecs == ["h264"]

    def test_persists_to_disk(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_hw_decode_codecs(["hevc", "h264"])

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["plex"]["hw_decode_codecs"] == ["h264", "hevc"]

    def test_round_trip(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")
        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config = Config()
            config.set_hw_decode_codecs(["av1", "vp9"])

        with patch("backend.config.CONFIG_FILE", config_file), \
             patch("backend.config.CONFIG_DIR", tmp_path):
            config2 = Config()
        assert config2.hw_decode_codecs == ["av1", "vp9"]

    def test_load_non_list_ignored(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, {"plex": {"hw_decode_codecs": "bad"}})
        assert config.hw_decode_codecs == []

    def test_load_filters_non_strings(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, {"plex": {"hw_decode_codecs": ["h264", 42, None]}})
        assert config.hw_decode_codecs == ["h264"]
