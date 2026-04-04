"""Tests for LiveTvLibrary (Live TV Guide backend).

Covers:
  - HDHomeRun device auth, lineup, and guide data fetching
  - Channel building from HDHomeRun guide API response
  - Current/next program assignment via StartTime/EndTime timestamps
  - HDHomeRun stream URL construction from DVR response
  - playChannel() calls mpv_launcher.launch_live_tv with correct URL
  - Guide cache: save/load roundtrip, missing, corrupt, clear
  - MpvLauncher.launch_live_tv builds correct args (reconnect, no http-header-fields)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = 1700000000  # fixed "now" for deterministic tests


def _make_guide_channel(
    vcn: str,
    name: str,
    affiliate: str = "",
    thumb: str = "",
    guide: list[dict] | None = None,
) -> dict:
    """Build a fake HDHomeRun guide channel entry.

    Each entry in *guide* should have StartTime, EndTime, Title, and optionally
    Synopsis and ImageURL.
    """
    ch: dict = {
        "GuideNumber": vcn,
        "GuideName": name,
    }
    if affiliate:
        ch["Affiliate"] = affiliate
    if thumb:
        ch["ImageURL"] = thumb
    if guide is not None:
        ch["Guide"] = guide
    return ch


def _make_guide_program(
    start: int,
    end: int,
    title: str,
    synopsis: str = "",
    prog_thumb: str = "",
) -> dict:
    """Build a fake HDHomeRun guide program entry."""
    prog: dict = {
        "StartTime": start,
        "EndTime": end,
        "Title": title,
    }
    if synopsis:
        prog["Synopsis"] = synopsis
    if prog_thumb:
        prog["ImageURL"] = prog_thumb
    return prog


def _make_dvr_response(host: str = "192.168.0.80") -> dict:
    """Build a fake /livetv/dvrs response."""
    return {
        "MediaContainer": {
            "Dvr": [
                {
                    "Device": [
                        {"uri": f"http://{host}:80"},
                    ]
                }
            ]
        }
    }


def _make_library(mock_client=None):
    """Create a LiveTvLibrary with a mock client factory."""
    from backend.live_tv_library import LiveTvLibrary

    if mock_client is None:
        mock_client = MagicMock()

    mock_launcher = MagicMock()
    lib = LiveTvLibrary(
        plex_client_factory=lambda: mock_client,
        mpv_launcher=mock_launcher,
    )
    return lib, mock_client, mock_launcher


# ---------------------------------------------------------------------------
# LiveTvLibrary._fetch_hdhomerun_host
# ---------------------------------------------------------------------------


class TestFetchHdhomerunHost:
    def test_extracts_host_from_dvr_uri(self) -> None:
        lib, client, _ = _make_library()
        client._get.return_value = _make_dvr_response("192.168.0.80")

        host = lib._fetch_hdhomerun_host(client)

        assert host == "192.168.0.80"

    def test_returns_empty_when_no_dvrs(self) -> None:
        lib, client, _ = _make_library()
        client._get.return_value = {"MediaContainer": {"Dvr": []}}

        host = lib._fetch_hdhomerun_host(client)

        assert host == ""

    def test_returns_empty_when_no_devices(self) -> None:
        lib, client, _ = _make_library()
        client._get.return_value = {
            "MediaContainer": {
                "Dvr": [{"Device": []}]
            }
        }

        host = lib._fetch_hdhomerun_host(client)

        assert host == ""

    def test_returns_empty_when_request_fails(self) -> None:
        lib, client, _ = _make_library()
        client._get.return_value = None

        host = lib._fetch_hdhomerun_host(client)

        assert host == ""

    def test_returns_empty_on_exception(self) -> None:
        lib, client, _ = _make_library()
        client._get.side_effect = RuntimeError("network error")

        host = lib._fetch_hdhomerun_host(client)

        assert host == ""


# ---------------------------------------------------------------------------
# LiveTvLibrary._fetch_device_auth
# ---------------------------------------------------------------------------


class TestFetchDeviceAuth:
    def test_returns_device_auth_from_discover(self) -> None:
        lib, _, _ = _make_library()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"DeviceAuth": "test-token-123"}
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.live_tv_library.requests.get", return_value=mock_resp) as mock_get:
            result = lib._fetch_device_auth("192.168.0.80")

        assert result == "test-token-123"
        mock_get.assert_called_once_with("http://192.168.0.80/discover.json", timeout=5)

    def test_returns_empty_on_failure(self) -> None:
        lib, _, _ = _make_library()

        with patch("backend.live_tv_library.requests.get", side_effect=Exception("fail")):
            result = lib._fetch_device_auth("192.168.0.80")

        assert result == ""


# ---------------------------------------------------------------------------
# LiveTvLibrary._fetch_lineup
# ---------------------------------------------------------------------------


class TestFetchLineup:
    def test_returns_dict_keyed_by_vcn(self) -> None:
        lib, _, _ = _make_library()

        lineup_data = [
            {"GuideNumber": "7.1", "GuideName": "WKBWDT", "URL": "http://192.168.0.80:5004/auto/v7.1"},
            {"GuideNumber": "4.1", "GuideName": "WIVBDT", "URL": "http://192.168.0.80:5004/auto/v4.1"},
            {"GuideNumber": "2.1", "GuideName": "WGRZ", "URL": "http://192.168.0.80:5004/auto/v2.1"},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = lineup_data
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.live_tv_library.requests.get", return_value=mock_resp) as mock_get:
            result = lib._fetch_lineup("192.168.0.80")

        assert len(result) == 3
        assert "7.1" in result
        assert "4.1" in result
        assert "2.1" in result
        assert result["7.1"]["GuideName"] == "WKBWDT"
        mock_get.assert_called_once_with("http://192.168.0.80/lineup.json", timeout=5)

    def test_returns_empty_on_failure(self) -> None:
        lib, _, _ = _make_library()

        with patch("backend.live_tv_library.requests.get", side_effect=Exception("fail")):
            result = lib._fetch_lineup("192.168.0.80")

        assert result == {}


# ---------------------------------------------------------------------------
# LiveTvLibrary._fetch_guide_data
# ---------------------------------------------------------------------------


class TestFetchGuideData:
    def test_returns_guide_list(self) -> None:
        lib, _, _ = _make_library()

        guide_data = [
            {"GuideNumber": "7.1", "GuideName": "WKBWDT", "Guide": []},
            {"GuideNumber": "4.1", "GuideName": "WIVBDT", "Guide": []},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = guide_data
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.live_tv_library.requests.get", return_value=mock_resp) as mock_get:
            result = lib._fetch_guide_data("test-token")

        assert result == guide_data
        mock_get.assert_called_once_with(
            "https://api.hdhomerun.com/api/guide",
            params={"DeviceAuth": "test-token"},
            timeout=15,
        )

    def test_returns_empty_on_failure(self) -> None:
        lib, _, _ = _make_library()

        with patch("backend.live_tv_library.requests.get", side_effect=Exception("fail")):
            result = lib._fetch_guide_data("test-token")

        assert result == []


# ---------------------------------------------------------------------------
# LiveTvLibrary._build_channels_from_guide
# ---------------------------------------------------------------------------


class TestBuildChannelsFromGuide:
    def test_current_program_detected_by_timestamp(self) -> None:
        """Program with StartTime <= now < EndTime is current."""
        lib, _, _ = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("7.1", "WKBWDT", "ABC", guide=[
                _make_guide_program(now - 1800, now + 1800, "Current Show", synopsis="A great show"),
                _make_guide_program(now + 1800, now + 5400, "Next Show"),
            ]),
        ]

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._build_channels_from_guide(guide_data, {}, "192.168.0.80")

        assert len(channels) == 1
        ch = channels[0]
        assert ch.current_program == "Current Show"
        assert ch.current_start == now - 1800
        assert ch.current_end == now + 1800
        assert ch.current_synopsis == "A great show"
        assert ch.on_air is True

    def test_next_program_is_first_after_now(self) -> None:
        """First program with StartTime > now is next."""
        lib, _, _ = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("7.1", "WKBWDT", "ABC", guide=[
                _make_guide_program(now - 1800, now + 1800, "Current Show"),
                _make_guide_program(now + 1800, now + 5400, "Next Show", synopsis="Coming up"),
                _make_guide_program(now + 5400, now + 9000, "Later Show"),
            ]),
        ]

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._build_channels_from_guide(guide_data, {}, "192.168.0.80")

        assert len(channels) == 1
        ch = channels[0]
        assert ch.next_program == "Next Show"
        assert ch.next_start == now + 1800
        assert ch.next_end == now + 5400
        assert ch.next_synopsis == "Coming up"

    def test_on_air_false_when_no_current_program(self) -> None:
        """on_air is False when no program is currently airing."""
        lib, _, _ = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("7.1", "WKBWDT", "ABC", guide=[
                _make_guide_program(now + 3600, now + 7200, "Future Show"),
            ]),
        ]

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._build_channels_from_guide(guide_data, {}, "192.168.0.80")

        assert len(channels) == 1
        ch = channels[0]
        assert ch.current_program == ""
        assert ch.on_air is False
        assert ch.next_program == "Future Show"

    def test_channel_title_includes_affiliate(self) -> None:
        """Title is "7.1 WKBWDT (ABC)" when affiliate is present."""
        lib, _, _ = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("7.1", "WKBWDT", "ABC", guide=[]),
        ]

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._build_channels_from_guide(guide_data, {}, "192.168.0.80")

        assert channels[0].title == "7.1 WKBWDT (ABC)"
        assert channels[0].affiliate == "ABC"

    def test_channel_title_without_affiliate(self) -> None:
        """Title is "7.1 WKBWDT" when no affiliate."""
        lib, _, _ = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("7.1", "WKBWDT", guide=[]),
        ]

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._build_channels_from_guide(guide_data, {}, "192.168.0.80")

        assert channels[0].title == "7.1 WKBWDT"
        assert channels[0].affiliate == ""

    def test_lineup_only_channel_excluded(self) -> None:
        """Channel in lineup but not in guide API response is excluded (no programme data)."""
        lib, _, _ = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("7.1", "WKBWDT", "ABC", guide=[]),
        ]
        lineup = {
            "7.1": {"GuideNumber": "7.1", "GuideName": "WKBWDT", "URL": "http://192.168.0.80:5004/auto/v7.1"},
            "99.1": {"GuideNumber": "99.1", "GuideName": "EXTRA", "URL": "http://192.168.0.80:5004/auto/v99.1"},
        }

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._build_channels_from_guide(guide_data, lineup, "192.168.0.80")

        # Only the guide channel is included; the lineup-only channel is hidden
        assert len(channels) == 1
        assert channels[0].vcn == "7.1"
        assert all(ch.vcn != "99.1" for ch in channels)

    def test_channels_sorted_by_vcn(self) -> None:
        """Result is sorted numerically by VCN."""
        lib, _, _ = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("49.4", "ION", guide=[]),
            _make_guide_channel("7.2", "Bounce", guide=[]),
            _make_guide_channel("13.1", "FOX", guide=[]),
            _make_guide_channel("7.1", "ABC", guide=[]),
        ]

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._build_channels_from_guide(guide_data, {}, "192.168.0.80")

        vcns = [ch.vcn for ch in channels]
        assert vcns == ["7.1", "7.2", "13.1", "49.4"]

    def test_stream_url_from_lineup(self) -> None:
        """Lineup URL takes priority over constructed URL."""
        lib, _, _ = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("7.1", "WKBWDT", "ABC", guide=[]),
        ]
        lineup = {
            "7.1": {"GuideNumber": "7.1", "GuideName": "WKBWDT", "URL": "http://10.0.0.1:5004/auto/v7.1"},
        }

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._build_channels_from_guide(guide_data, lineup, "192.168.0.80")

        assert channels[0].stream_url == "http://10.0.0.1:5004/auto/v7.1"

    def test_program_thumb_and_channel_thumb(self) -> None:
        """Channel thumb and program thumb are correctly assigned."""
        lib, _, _ = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("7.1", "WKBWDT", "ABC",
                                thumb="http://img.example.com/abc_logo.png",
                                guide=[
                                    _make_guide_program(now - 1800, now + 1800, "Show",
                                                        prog_thumb="http://img.example.com/show.png"),
                                ]),
        ]

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._build_channels_from_guide(guide_data, {}, "192.168.0.80")

        ch = channels[0]
        assert ch.thumb == "http://img.example.com/abc_logo.png"
        assert ch.current_thumb == "http://img.example.com/show.png"


# ---------------------------------------------------------------------------
# LiveTvLibrary.playChannel
# ---------------------------------------------------------------------------


class TestPlayChannel:
    def test_play_channel_calls_launch_live_tv_with_correct_url(self) -> None:
        """playChannel() calls mpv_launcher.launch_live_tv with the correct stream URL."""
        lib, _, mock_launcher = _make_library()

        now = _NOW
        guide_data = [
            _make_guide_channel("7.1", "WKBWDT", "ABC", guide=[
                _make_guide_program(now - 1800, now + 1800, "Current Show"),
            ]),
        ]

        with patch("backend.live_tv_library.time.time", return_value=now):
            lib._channels = lib._build_channels_from_guide(guide_data, {}, "192.168.0.80")
        lib._hdhomerun_host = "192.168.0.80"

        lib.playChannel("7.1")

        mock_launcher.launch_live_tv.assert_called_once_with(
            "http://192.168.0.80:5004/auto/v7.1",
            "7.1 WKBWDT (ABC)",
        )

    def test_play_channel_uses_vcn_as_title_when_channel_not_found(self) -> None:
        """playChannel() uses the VCN as title when the channel is not in the model."""
        lib, _, mock_launcher = _make_library()
        lib._hdhomerun_host = "192.168.0.80"
        lib._channels = []

        lib.playChannel("99.1")

        mock_launcher.launch_live_tv.assert_called_once_with(
            "http://192.168.0.80:5004/auto/v99.1",
            "99.1",
        )

    def test_play_channel_does_nothing_when_no_host_and_no_channel(self) -> None:
        """playChannel() does nothing when no HDHomeRun host and no channel with stream_url."""
        lib, _, mock_launcher = _make_library()
        lib._hdhomerun_host = ""
        lib._channels = []

        lib.playChannel("7.1")

        mock_launcher.launch_live_tv.assert_not_called()


# ---------------------------------------------------------------------------
# Guide cache
# ---------------------------------------------------------------------------


class TestGuideCache:
    """Tests for the guide cache (save/load roundtrip, missing, corrupt, clear)."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Save channels, load them back, verify all fields."""
        import backend.live_tv_library as mod
        from backend.live_tv_models import LiveTvChannel

        lib, _, _ = _make_library()

        channels = [
            LiveTvChannel(
                channel_id=0,
                vcn="7.1",
                title="7.1 WKBWDT (ABC)",
                call_sign="WKBWDT",
                thumb="http://img.example.com/abc.png",
                grid_key="",
                stream_url="http://192.168.0.80:5004/auto/v7.1",
                current_program="Current Show",
                current_start=_NOW - 1800,
                current_end=_NOW + 1800,
                current_thumb="http://img.example.com/show.png",
                next_program="Next Show",
                next_start=_NOW + 1800,
                next_end=_NOW + 5400,
                next_thumb="",
                on_air=True,
                affiliate="ABC",
                current_synopsis="A great show",
                next_synopsis="Coming up next",
            ),
        ]

        with patch.object(mod, "_CACHE_DIR", tmp_path):
            lib._save_guide_cache(channels)
            loaded = lib._load_guide_cache("192.168.0.80")

        assert len(loaded) == 1
        ch = loaded[0]
        assert ch.vcn == "7.1"
        assert ch.title == "7.1 WKBWDT (ABC)"
        assert ch.call_sign == "WKBWDT"
        assert ch.affiliate == "ABC"
        assert ch.thumb == "http://img.example.com/abc.png"
        assert ch.stream_url == "http://192.168.0.80:5004/auto/v7.1"
        assert ch.current_program == "Current Show"
        assert ch.current_start == _NOW - 1800
        assert ch.current_end == _NOW + 1800
        assert ch.current_thumb == "http://img.example.com/show.png"
        assert ch.current_synopsis == "A great show"
        assert ch.next_program == "Next Show"
        assert ch.next_start == _NOW + 1800
        assert ch.next_end == _NOW + 5400
        assert ch.next_synopsis == "Coming up next"
        assert ch.on_air is True

    def test_load_returns_empty_when_missing(self, tmp_path: Path) -> None:
        """Returns [] when guide_cache.json does not exist."""
        import backend.live_tv_library as mod

        lib, _, _ = _make_library()

        with patch.object(mod, "_CACHE_DIR", tmp_path):
            loaded = lib._load_guide_cache("192.168.0.80")

        assert loaded == []

    def test_load_returns_empty_on_corrupt_json(self, tmp_path: Path) -> None:
        """Returns [] when guide_cache.json contains invalid JSON."""
        import backend.live_tv_library as mod

        lib, _, _ = _make_library()

        (tmp_path / "guide_cache.json").write_text("not valid json{{{", encoding="utf-8")

        with patch.object(mod, "_CACHE_DIR", tmp_path):
            loaded = lib._load_guide_cache("192.168.0.80")

        assert loaded == []

    def test_clear_cache_removes_guide_cache_file(self, tmp_path: Path) -> None:
        """_clear_cache() removes guide_cache.json."""
        import backend.live_tv_library as mod

        lib, _, _ = _make_library()

        (tmp_path / "guide_cache.json").write_text("[]", encoding="utf-8")
        (tmp_path / "old_channels.json").write_text("[]", encoding="utf-8")

        with patch.object(mod, "_CACHE_DIR", tmp_path):
            lib._clear_cache()

        remaining = list(tmp_path.iterdir())
        assert remaining == []


# ---------------------------------------------------------------------------
# MpvLauncher.launch_live_tv — arg construction
# ---------------------------------------------------------------------------


class TestMpvLauncherLiveTv:
    def test_launch_live_tv_uses_reconnect_args(self, tmp_path: Path) -> None:
        """launch_live_tv() includes reconnect options for live streams."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch_live_tv("http://192.168.0.80:5004/auto/v7.1", "ABC")

        mock_process.start.assert_called_once()
        program, args = mock_process.start.call_args[0]
        assert program == "/usr/bin/mpv"
        assert "--fullscreen" in args
        assert "--no-terminal" in args
        assert any(a.startswith("--hwdec=vaapi") for a in args)  # vaapi or vaapi-copy
        assert "--vo=gpu" in args
        assert any(a.startswith("--gpu-context=") for a in args)  # x11 or wayland
        assert "--cache=yes" in args
        assert "--demuxer-max-bytes=128MiB" in args
        assert any("reconnect=1" in a for a in args)
        assert "http://192.168.0.80:5004/auto/v7.1" in args

    def test_launch_live_tv_has_no_http_header_fields(self, tmp_path: Path) -> None:
        """launch_live_tv() does NOT include --http-header-fields (no auth needed)."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch_live_tv("http://192.168.0.80:5004/auto/v7.1")

        _, args = mock_process.start.call_args[0]
        assert not any("http-header-fields" in a for a in args)

    def test_launch_live_tv_has_no_start_arg(self, tmp_path: Path) -> None:
        """launch_live_tv() does NOT include --start (live streams start at live edge)."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch_live_tv("http://192.168.0.80:5004/auto/v7.1")

        _, args = mock_process.start.call_args[0]
        assert not any(a.startswith("--start=") for a in args)

    def test_launch_live_tv_includes_title_when_given(self, tmp_path: Path) -> None:
        """launch_live_tv() includes --title and --force-media-title when title is given."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.return_value = QProcess.ProcessState.NotRunning

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch_live_tv("http://192.168.0.80:5004/auto/v7.1", "ABC Channel")

        _, args = mock_process.start.call_args[0]
        assert "--title=ABC Channel" in args
        assert "--force-media-title=ABC Channel" in args

    def test_launch_live_tv_noop_when_already_running(self, tmp_path: Path) -> None:
        """launch_live_tv() is a no-op when MPV is already running."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod
        from PySide6.QtCore import QProcess

        input_conf_path = tmp_path / "mpv" / "input.conf"

        mock_process = MagicMock(spec=QProcess)
        mock_process.state.side_effect = [
            QProcess.ProcessState.NotRunning,  # before first launch
            QProcess.ProcessState.Running,     # before second launch
        ]

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path), \
             patch("backend.mpv_launcher.QProcess", return_value=mock_process):
            launcher = MpvLauncher()
            launcher.launch_live_tv("http://192.168.0.80:5004/auto/v7.1")
            launcher.launch_live_tv("http://192.168.0.80:5004/auto/v4.1")

        assert mock_process.start.call_count == 1

    def test_build_live_tv_args_uses_128mib_buffer(self, tmp_path: Path) -> None:
        """_build_live_tv_args uses 128MiB demuxer buffer (larger than VOD's 50MiB)."""
        from backend.mpv_launcher import MpvLauncher
        import backend.mpv_launcher as mpv_mod

        input_conf_path = tmp_path / "mpv" / "input.conf"

        with patch.object(mpv_mod, "_INPUT_CONF_PATH", input_conf_path):
            launcher = MpvLauncher()
            args = launcher._build_live_tv_args("http://192.168.0.80:5004/auto/v7.1")

        assert "--demuxer-max-bytes=128MiB" in args
        # VOD uses 50MiB — live TV should NOT use 50MiB
        assert "--demuxer-max-bytes=50MiB" not in args


# ---------------------------------------------------------------------------
# LiveTvChannelModel — roles and data
# ---------------------------------------------------------------------------


class TestLiveTvChannelModel:
    def _make_channel(
        self,
        vcn: str = "7.1",
        title: str = "ABC",
        channel_id: int = 1,
    ):
        from backend.live_tv_models import LiveTvChannel

        return LiveTvChannel(
            channel_id=channel_id,
            vcn=vcn,
            title=title,
            call_sign=title,
            thumb="http://thumb.example.com/abc.png",
            grid_key="gk1",
            stream_url=f"http://192.168.0.80:5004/auto/v{vcn}",
            current_program="Current Show",
            current_start=_NOW - 1800,
            current_end=_NOW + 1800,
            current_thumb="http://prog.example.com/show.png",
            next_program="Next Show",
            next_start=_NOW + 1800,
            next_end=_NOW + 5400,
            next_thumb="",
            on_air=True,
        )

    def test_roles_and_data(self) -> None:
        from backend.live_tv_library import LiveTvChannelModel
        from PySide6.QtCore import QModelIndex

        model = LiveTvChannelModel()
        ch = self._make_channel("7.1", "ABC", 42)
        model.set_channels([ch])

        assert model.rowCount() == 1

        idx = model.index(0, 0)
        assert model.data(idx, LiveTvChannelModel.ChannelIdRole) == 42
        assert model.data(idx, LiveTvChannelModel.VcnRole) == "7.1"
        assert model.data(idx, LiveTvChannelModel.TitleRole) == "ABC"
        assert model.data(idx, LiveTvChannelModel.CallSignRole) == "ABC"
        assert model.data(idx, LiveTvChannelModel.ThumbRole) == "http://thumb.example.com/abc.png"
        assert model.data(idx, LiveTvChannelModel.StreamUrlRole) == "http://192.168.0.80:5004/auto/v7.1"
        assert model.data(idx, LiveTvChannelModel.CurrentProgramRole) == "Current Show"
        assert model.data(idx, LiveTvChannelModel.CurrentStartRole) == _NOW - 1800
        assert model.data(idx, LiveTvChannelModel.CurrentEndRole) == _NOW + 1800
        assert model.data(idx, LiveTvChannelModel.CurrentThumbRole) == "http://prog.example.com/show.png"
        assert model.data(idx, LiveTvChannelModel.NextProgramRole) == "Next Show"
        assert model.data(idx, LiveTvChannelModel.NextStartRole) == _NOW + 1800
        assert model.data(idx, LiveTvChannelModel.NextEndRole) == _NOW + 5400
        assert model.data(idx, LiveTvChannelModel.NextThumbRole) == ""
        assert model.data(idx, LiveTvChannelModel.OnAirRole) is True
        assert model.data(idx, LiveTvChannelModel.AffiliateRole) == ""
        assert model.data(idx, LiveTvChannelModel.CurrentSynopsisRole) == ""
        assert model.data(idx, LiveTvChannelModel.NextSynopsisRole) == ""

    def test_role_names(self) -> None:
        from backend.live_tv_library import LiveTvChannelModel

        model = LiveTvChannelModel()
        names = model.roleNames()
        assert b"channelId" in names.values()
        assert b"vcn" in names.values()
        assert b"title" in names.values()
        assert b"callSign" in names.values()
        assert b"thumb" in names.values()
        assert b"streamUrl" in names.values()
        assert b"currentProgram" in names.values()
        assert b"nextProgram" in names.values()
        assert b"onAir" in names.values()
        assert b"affiliate" in names.values()
        assert b"currentSynopsis" in names.values()
        assert b"nextSynopsis" in names.values()

    def test_invalid_index_returns_none(self) -> None:
        from backend.live_tv_library import LiveTvChannelModel
        from PySide6.QtCore import QModelIndex

        model = LiveTvChannelModel()
        assert model.data(QModelIndex(), LiveTvChannelModel.TitleRole) is None

    def test_set_channels_replaces_model(self) -> None:
        from backend.live_tv_library import LiveTvChannelModel

        model = LiveTvChannelModel()
        model.set_channels([self._make_channel("7.1", "ABC", 1)])
        assert model.rowCount() == 1

        model.set_channels([
            self._make_channel("7.1", "ABC", 1),
            self._make_channel("4.1", "NBC", 2),
        ])
        assert model.rowCount() == 2
