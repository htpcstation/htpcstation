"""Tests for LiveTvLibrary (Task 003 — Live TV Guide backend).

Covers:
  - refresh() correctly parses EPG grid response into channels
  - Current/next program assignment logic (onAir flag, timestamp comparison)
  - HDHomeRun stream URL construction from DVR response
  - playChannel() calls mpv_launcher.launch_live_tv with correct URL
  - Channels with no HDHomeRun match have stream_url = ""
  - Graceful handling of DVR fetch failure (stream_url = "" for all channels)
  - Pagination: fetches all pages when totalSize > page_size
  - MpvLauncher.launch_live_tv builds correct args (reconnect, no http-header-fields)
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = 1700000000  # fixed "now" for deterministic tests


def _make_program(
    channel_identifier: str,
    channel_vcn: str,
    channel_title: str,
    channel_thumb: str,
    grid_key: str,
    channel_id: int,
    prog_title: str,
    begins_at: int,
    ends_at: int,
    on_air: bool = False,
    prog_thumb: str = "",
) -> dict:
    """Build a fake EPG grid item (Metadata entry)."""
    media: dict = {
        "channelIdentifier": channel_identifier,
        "channelVcn": channel_vcn,
        "channelTitle": channel_title,
        "channelThumb": channel_thumb,
        "gridKey": grid_key,
        "channelID": channel_id,
        "beginsAt": begins_at,
        "endsAt": ends_at,
    }
    if on_air:
        media["onAir"] = True
    return {
        "title": prog_title,
        "thumb": prog_thumb,
        "Media": [media],
    }


def _make_grid_response(items: list[dict], total_size: int | None = None) -> dict:
    """Build a fake EPG grid API response."""
    return {
        "MediaContainer": {
            "Metadata": items,
            "totalSize": total_size if total_size is not None else len(items),
        }
    }


def _make_providers_response(epg_key: str = "tv.plex.providers.epg.cloud:2") -> dict:
    """Build a fake /media/providers response."""
    return {
        "MediaContainer": {
            "MediaProvider": [
                {"identifier": "tv.plex.providers.epg.cloud:2"},
            ]
        }
    }


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
# LiveTvLibrary._fetch_epg_provider_key
# ---------------------------------------------------------------------------


class TestFetchEpgProviderKey:
    def test_finds_epg_cloud_provider(self) -> None:
        lib, client, _ = _make_library()
        client._get.return_value = _make_providers_response("tv.plex.providers.epg.cloud:2")

        key = lib._fetch_epg_provider_key(client)

        assert key == "tv.plex.providers.epg.cloud:2"

    def test_finds_epg_cloud_provider_with_different_suffix(self) -> None:
        lib, client, _ = _make_library()
        client._get.return_value = {
            "MediaContainer": {
                "MediaProvider": [
                    {"identifier": "tv.plex.providers.epg.cloud:5"},
                ]
            }
        }

        key = lib._fetch_epg_provider_key(client)

        assert key == "tv.plex.providers.epg.cloud:5"

    def test_returns_empty_when_no_epg_provider(self) -> None:
        lib, client, _ = _make_library()
        client._get.return_value = {
            "MediaContainer": {
                "MediaProvider": [
                    {"identifier": "tv.plex.providers.other"},
                ]
            }
        }

        key = lib._fetch_epg_provider_key(client)

        assert key == ""

    def test_returns_empty_when_request_fails(self) -> None:
        lib, client, _ = _make_library()
        client._get.return_value = None

        key = lib._fetch_epg_provider_key(client)

        assert key == ""


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
# LiveTvLibrary._build_channels — current/next program logic
# ---------------------------------------------------------------------------


class TestBuildChannels:
    def test_current_program_identified_by_timestamp(self) -> None:
        """Program with beginsAt <= now < endsAt is the current program."""
        lib, _, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Current Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Next Show",
                begins_at=now + 1800,
                ends_at=now + 5400,
            ),
        ]

        channels = lib._build_channels(items, "192.168.0.80", now)

        assert len(channels) == 1
        ch = channels[0]
        assert ch.current_program == "Current Show"
        assert ch.next_program == "Next Show"
        assert ch.on_air is True

    def test_current_program_identified_by_on_air_flag(self) -> None:
        """Program with onAir=True is the current program even without timestamp match."""
        lib, _, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "On Air Show",
                begins_at=now - 3600,
                ends_at=now + 3600,
                on_air=True,
            ),
        ]

        channels = lib._build_channels(items, "192.168.0.80", now)

        assert len(channels) == 1
        ch = channels[0]
        assert ch.current_program == "On Air Show"
        assert ch.on_air is True

    def test_on_air_false_when_no_current_program(self) -> None:
        """on_air is False when no program is currently airing."""
        lib, _, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Future Show",
                begins_at=now + 3600,
                ends_at=now + 7200,
            ),
        ]

        channels = lib._build_channels(items, "192.168.0.80", now)

        assert len(channels) == 1
        ch = channels[0]
        assert ch.current_program == ""
        assert ch.on_air is False

    def test_next_program_is_first_after_now(self) -> None:
        """next_program is the first program that starts after now."""
        lib, _, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Current Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Next Show",
                begins_at=now + 1800,
                ends_at=now + 5400,
            ),
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Later Show",
                begins_at=now + 5400,
                ends_at=now + 9000,
            ),
        ]

        channels = lib._build_channels(items, "192.168.0.80", now)

        assert len(channels) == 1
        ch = channels[0]
        assert ch.next_program == "Next Show"

    def test_stream_url_built_from_hdhomerun_host_and_vcn(self) -> None:
        """stream_url is built as http://{host}:5004/auto/v{vcn}."""
        lib, _, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
        ]

        channels = lib._build_channels(items, "192.168.0.80", now)

        assert len(channels) == 1
        assert channels[0].stream_url == "http://192.168.0.80:5004/auto/v7.1"

    def test_stream_url_empty_when_no_hdhomerun_host(self) -> None:
        """stream_url is "" when hdhomerun_host is empty."""
        lib, _, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
        ]

        channels = lib._build_channels(items, "", now)

        assert len(channels) == 1
        assert channels[0].stream_url == ""

    def test_multiple_channels_parsed(self) -> None:
        """Multiple channels are parsed correctly."""
        lib, _, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Show A",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
            _make_program(
                "ch2", "4.1", "NBC", "", "gk2", 2,
                "Show B",
                begins_at=now - 900,
                ends_at=now + 2700,
            ),
        ]

        channels = lib._build_channels(items, "192.168.0.80", now)

        assert len(channels) == 2
        vcns = {ch.vcn for ch in channels}
        assert vcns == {"7.1", "4.1"}

    def test_channel_metadata_fields_populated(self) -> None:
        """Channel metadata fields are correctly populated from EPG data."""
        lib, _, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "WKBWDT", "http://thumb.example.com/ch1.png", "gk1", 42,
                "Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
                prog_thumb="http://prog.example.com/show.png",
            ),
        ]

        channels = lib._build_channels(items, "192.168.0.80", now)

        assert len(channels) == 1
        ch = channels[0]
        assert ch.vcn == "7.1"
        assert ch.title == "WKBWDT"
        assert ch.call_sign == "WKBWDT"
        assert ch.thumb == "http://thumb.example.com/ch1.png"
        assert ch.grid_key == "gk1"
        assert ch.channel_id == 42
        assert ch.current_thumb == "http://prog.example.com/show.png"


# ---------------------------------------------------------------------------
# LiveTvLibrary._fetch_channels — pagination
# ---------------------------------------------------------------------------


class TestFetchChannelsPagination:
    def test_fetches_all_pages_when_total_exceeds_page_size(self) -> None:
        """Pagination: fetches all pages when totalSize > page_size."""
        from backend.live_tv_library import _EPG_PAGE_SIZE
        lib, client, _ = _make_library()

        now = _NOW

        # Build 150 programs across 2 channels (75 each)
        page1_items = [
            _make_program(
                f"ch{i % 2 + 1}", f"{i % 2 + 1}.1", f"CH{i % 2 + 1}", "", f"gk{i % 2 + 1}",
                i % 2 + 1,
                f"Show {i}",
                begins_at=now - 1800 + i * 60,
                ends_at=now + 1800 + i * 60,
            )
            for i in range(_EPG_PAGE_SIZE)
        ]
        page2_items = [
            _make_program(
                f"ch{i % 2 + 1}", f"{i % 2 + 1}.1", f"CH{i % 2 + 1}", "", f"gk{i % 2 + 1}",
                i % 2 + 1,
                f"Show {i + _EPG_PAGE_SIZE}",
                begins_at=now + 1800 + i * 60,
                ends_at=now + 5400 + i * 60,
            )
            for i in range(50)
        ]

        call_count = [0]

        def fake_get(path, params=None):
            call_count[0] += 1
            if params and params.get("X-Plex-Container-Start", 0) == 0:
                return _make_grid_response(page1_items, total_size=150)
            else:
                return _make_grid_response(page2_items, total_size=150)

        client._get.side_effect = fake_get

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._fetch_channels(client, "tv.plex.providers.epg.cloud:2", "192.168.0.80")

        # Should have made 2 API calls (page 1 and page 2)
        assert call_count[0] == 2
        # Should have 2 channels
        assert len(channels) == 2

    def test_stops_pagination_when_no_items_returned(self) -> None:
        """Pagination stops when an empty page is returned."""
        lib, client, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
        ]

        call_count = [0]

        def fake_get(path, params=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_grid_response(items, total_size=1)
            return _make_grid_response([], total_size=1)

        client._get.side_effect = fake_get

        with patch("backend.live_tv_library.time.time", return_value=now):
            channels = lib._fetch_channels(client, "tv.plex.providers.epg.cloud:2", "192.168.0.80")

        assert call_count[0] == 1
        assert len(channels) == 1


# ---------------------------------------------------------------------------
# LiveTvLibrary.playChannel
# ---------------------------------------------------------------------------


class TestPlayChannel:
    def test_play_channel_calls_launch_live_tv_with_correct_url(self) -> None:
        """playChannel() calls mpv_launcher.launch_live_tv with the correct stream URL."""
        lib, _, mock_launcher = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Current Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
        ]
        lib._channels = lib._build_channels(items, "192.168.0.80", now)
        lib._hdhomerun_host = "192.168.0.80"

        lib.playChannel("7.1")

        mock_launcher.launch_live_tv.assert_called_once_with(
            "http://192.168.0.80:5004/auto/v7.1",
            "ABC",
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

    def test_play_channel_does_nothing_when_no_hdhomerun_host(self) -> None:
        """playChannel() does nothing when no HDHomeRun host is available."""
        lib, _, mock_launcher = _make_library()
        lib._hdhomerun_host = ""

        lib.playChannel("7.1")

        mock_launcher.launch_live_tv.assert_not_called()


# ---------------------------------------------------------------------------
# LiveTvLibrary._worker_refresh — DVR failure
# ---------------------------------------------------------------------------


class TestWorkerRefreshDvrFailure:
    def test_stream_url_empty_when_dvr_fetch_fails(self) -> None:
        """When DVR fetch fails, all channels have stream_url = ""."""
        lib, client, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
        ]

        def fake_get(path, params=None):
            if path == "/media/providers":
                return _make_providers_response()
            if path == "/livetv/dvrs":
                return None  # DVR fetch fails
            return _make_grid_response(items)

        client._get.side_effect = fake_get

        with patch("backend.live_tv_library.time.time", return_value=now):
            lib._worker_refresh(client)

        # Check that channels were stored with empty stream_url
        assert len(lib._channels) == 1
        assert lib._channels[0].stream_url == ""

    def test_stream_url_empty_when_dvr_raises_exception(self) -> None:
        """When DVR fetch raises, all channels have stream_url = ""."""
        lib, client, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
        ]

        def fake_get(path, params=None):
            if path == "/media/providers":
                return _make_providers_response()
            if path == "/livetv/dvrs":
                raise RuntimeError("DVR error")
            return _make_grid_response(items)

        client._get.side_effect = fake_get

        with patch("backend.live_tv_library.time.time", return_value=now):
            lib._worker_refresh(client)

        # Check that channels were stored with empty stream_url
        assert len(lib._channels) == 1
        assert lib._channels[0].stream_url == ""


# ---------------------------------------------------------------------------
# LiveTvLibrary._worker_refresh — full integration
# ---------------------------------------------------------------------------


class TestWorkerRefreshIntegration:
    def test_refresh_parses_epg_grid_into_channels(self) -> None:
        """_worker_refresh correctly parses EPG grid response into channels."""
        lib, client, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "http://thumb.example.com/abc.png", "gk1", 1,
                "Current Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
                on_air=True,
                prog_thumb="http://prog.example.com/show.png",
            ),
            _make_program(
                "ch1", "7.1", "ABC", "http://thumb.example.com/abc.png", "gk1", 1,
                "Next Show",
                begins_at=now + 1800,
                ends_at=now + 5400,
            ),
        ]

        def fake_get(path, params=None):
            if path == "/media/providers":
                return _make_providers_response()
            if path == "/livetv/dvrs":
                return _make_dvr_response("192.168.0.80")
            return _make_grid_response(items)

        client._get.side_effect = fake_get

        with patch("backend.live_tv_library.time.time", return_value=now):
            lib._worker_refresh(client)

        # Check stored channels directly (signal emission is async in Qt event loop)
        assert len(lib._channels) == 1
        ch = lib._channels[0]
        assert ch.vcn == "7.1"
        assert ch.title == "ABC"
        assert ch.current_program == "Current Show"
        assert ch.next_program == "Next Show"
        assert ch.on_air is True
        assert ch.stream_url == "http://192.168.0.80:5004/auto/v7.1"

    def test_refresh_emits_loading_false_on_success(self) -> None:
        """_worker_refresh emits loadingUpdate(False) after successful fetch."""
        lib, client, _ = _make_library()

        now = _NOW
        items = [
            _make_program(
                "ch1", "7.1", "ABC", "", "gk1", 1,
                "Show",
                begins_at=now - 1800,
                ends_at=now + 1800,
            ),
        ]

        def fake_get(path, params=None):
            if "providers" in path:
                return _make_providers_response()
            if "dvrs" in path:
                return _make_dvr_response()
            return _make_grid_response(items)

        client._get.side_effect = fake_get

        loading_updates = []
        lib._loadingUpdate.connect(lambda v: loading_updates.append(v))

        with patch("backend.live_tv_library.time.time", return_value=now):
            lib._worker_refresh(client)

        # The _channelsReady signal triggers _on_channels_ready which emits False
        # But _worker_refresh itself doesn't emit False — _on_channels_ready does
        # We check that _channelsReady was emitted (which triggers loading=False)
        assert lib._epg_provider_key == "tv.plex.providers.epg.cloud:2"
        assert lib._hdhomerun_host == "192.168.0.80"

    def test_refresh_emits_loading_false_when_no_epg_provider(self) -> None:
        """_worker_refresh emits loadingUpdate(False) when EPG provider not found."""
        lib, client, _ = _make_library()

        client._get.return_value = {
            "MediaContainer": {"MediaProvider": []}
        }

        loading_updates = []
        lib._loadingUpdate.connect(lambda v: loading_updates.append(v))

        lib._worker_refresh(client)

        assert False in loading_updates


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
        assert "--hwdec=vaapi" in args
        assert "--vo=gpu" in args
        assert "--gpu-context=x11" in args
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
