"""Live TV library manager for HTPC Station.

Fetches guide data from the HDHomeRun device and SiliconDust cloud API,
then exposes a channel guide model to QML.
All network calls happen off the main thread using a ThreadPoolExecutor.
Models are updated on the main thread only.

Guide data is cached to disk so the guide can be served
instantly on warm start, then refreshed in the background.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional
from urllib.parse import urlparse

import requests

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from backend.config import CONFIG_DIR
from backend.live_tv_models import LiveTvChannel
from backend.mpv_launcher import MpvLauncher

logger = logging.getLogger(__name__)

_CACHE_DIR = CONFIG_DIR / "livetv_cache"


# ---------------------------------------------------------------------------
# LiveTvChannelModel
# ---------------------------------------------------------------------------


class LiveTvChannelModel(QAbstractListModel):
    """QML model for Live TV channels.

    Roles: channelId, vcn, title, callSign, thumb, streamUrl,
           currentProgram, currentStart, currentEnd, currentThumb,
           nextProgram, nextStart, nextEnd, nextThumb, onAir,
           affiliate, currentSynopsis, nextSynopsis
    """

    ChannelIdRole = Qt.ItemDataRole.UserRole + 1
    VcnRole = Qt.ItemDataRole.UserRole + 2
    TitleRole = Qt.ItemDataRole.UserRole + 3
    CallSignRole = Qt.ItemDataRole.UserRole + 4
    ThumbRole = Qt.ItemDataRole.UserRole + 5
    StreamUrlRole = Qt.ItemDataRole.UserRole + 6
    CurrentProgramRole = Qt.ItemDataRole.UserRole + 7
    CurrentStartRole = Qt.ItemDataRole.UserRole + 8
    CurrentEndRole = Qt.ItemDataRole.UserRole + 9
    CurrentThumbRole = Qt.ItemDataRole.UserRole + 10
    NextProgramRole = Qt.ItemDataRole.UserRole + 11
    NextStartRole = Qt.ItemDataRole.UserRole + 12
    NextEndRole = Qt.ItemDataRole.UserRole + 13
    NextThumbRole = Qt.ItemDataRole.UserRole + 14
    OnAirRole = Qt.ItemDataRole.UserRole + 15
    AffiliateRole = Qt.ItemDataRole.UserRole + 16
    CurrentSynopsisRole = Qt.ItemDataRole.UserRole + 17
    NextSynopsisRole = Qt.ItemDataRole.UserRole + 18

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._channels: list[LiveTvChannel] = []

    def set_channels(self, channels: list[LiveTvChannel]) -> None:
        """Replace the model contents. Must be called on the main thread."""
        self.beginResetModel()
        self._channels = channels
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._channels)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._channels)):
            return None
        ch = self._channels[index.row()]
        if role == self.ChannelIdRole:
            return ch.channel_id
        if role == self.VcnRole:
            return ch.vcn
        if role == self.TitleRole:
            return ch.title
        if role == self.CallSignRole:
            return ch.call_sign
        if role == self.ThumbRole:
            return ch.thumb
        if role == self.StreamUrlRole:
            return ch.stream_url
        if role == self.CurrentProgramRole:
            return ch.current_program
        if role == self.CurrentStartRole:
            return ch.current_start
        if role == self.CurrentEndRole:
            return ch.current_end
        if role == self.CurrentThumbRole:
            return ch.current_thumb
        if role == self.NextProgramRole:
            return ch.next_program
        if role == self.NextStartRole:
            return ch.next_start
        if role == self.NextEndRole:
            return ch.next_end
        if role == self.NextThumbRole:
            return ch.next_thumb
        if role == self.OnAirRole:
            return ch.on_air
        if role == self.AffiliateRole:
            return ch.affiliate
        if role == self.CurrentSynopsisRole:
            return ch.current_synopsis
        if role == self.NextSynopsisRole:
            return ch.next_synopsis
        if role == Qt.ItemDataRole.DisplayRole:
            return ch.title
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.ChannelIdRole: b"channelId",
            self.VcnRole: b"vcn",
            self.TitleRole: b"title",
            self.CallSignRole: b"callSign",
            self.ThumbRole: b"thumb",
            self.StreamUrlRole: b"streamUrl",
            self.CurrentProgramRole: b"currentProgram",
            self.CurrentStartRole: b"currentStart",
            self.CurrentEndRole: b"currentEnd",
            self.CurrentThumbRole: b"currentThumb",
            self.NextProgramRole: b"nextProgram",
            self.NextStartRole: b"nextStart",
            self.NextEndRole: b"nextEnd",
            self.NextThumbRole: b"nextThumb",
            self.OnAirRole: b"onAir",
            self.AffiliateRole: b"affiliate",
            self.CurrentSynopsisRole: b"currentSynopsis",
            self.NextSynopsisRole: b"nextSynopsis",
        }


# ---------------------------------------------------------------------------
# LiveTvLibrary
# ---------------------------------------------------------------------------


class LiveTvLibrary(QObject):
    """Manages Live TV guide data and exposes it to QML.

    Exposed to QML as the ``liveTV`` context property.

    All network calls are dispatched to a ThreadPoolExecutor.
    Results are delivered back to the main thread via Qt signals.
    """

    channelsChanged = Signal()
    loadingChanged = Signal(bool)

    # Internal signals used to marshal results from worker threads to main thread
    _channelsReady = Signal(list)
    _loadingUpdate = Signal(bool)

    def __init__(
        self,
        plex_client_factory: Callable,
        mpv_launcher: MpvLauncher,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self._plex_client_factory = plex_client_factory
        self._mpv_launcher = mpv_launcher
        self._loading = False
        self._hdhomerun_host: str = ""
        self._channels: list[LiveTvChannel] = []

        # Build model
        self._channels_model = LiveTvChannelModel(self)

        # Thread pool for network calls
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Connect internal signals (worker -> main thread)
        self._channelsReady.connect(self._on_channels_ready)
        self._loadingUpdate.connect(self._on_loading_update)

    # ------------------------------------------------------------------
    # Q_PROPERTYs
    # ------------------------------------------------------------------

    channelsModel = Property(
        QObject,
        fget=lambda self: self._channels_model,
        notify=channelsChanged,
    )
    loading = Property(
        bool,
        fget=lambda self: self._loading,
        notify=loadingChanged,
    )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        """Fetch HDHomeRun host, guide data, and build channel list."""
        client = self._plex_client_factory()
        # If we already know the host, we can refresh without a Plex client
        if client is None and not self._hdhomerun_host:
            logger.info("LiveTvLibrary.refresh: no Plex client and no cached host")
            return
        self._loadingUpdate.emit(True)
        self._executor.submit(self._worker_refresh, client)

    @Slot()
    def forceRefresh(self) -> None:
        """Clear guide cache and re-fetch everything."""
        self._clear_cache()
        self.refresh()

    @Slot(str)
    def playChannel(self, vcn: str) -> None:
        """Launch MPV with the HDHomeRun direct stream for the given channel VCN."""
        channel = self._channel_by_vcn(vcn)
        if channel and channel.stream_url:
            stream_url = channel.stream_url
        elif self._hdhomerun_host:
            stream_url = f"http://{self._hdhomerun_host}:5004/auto/v{vcn}"
        else:
            logger.warning("LiveTvLibrary.playChannel: no stream URL for vcn=%s", vcn)
            return
        title = channel.title if channel else vcn
        logger.info("LiveTvLibrary.playChannel: launching MPV for '%s' url=%s", title, stream_url)
        self._mpv_launcher.launch_live_tv(stream_url, title)

    @Slot(str)
    def playChannelBrowser(self, vcn: str) -> None:
        """Launch the kiosk browser for Live TV (fallback).

        This is a stub — the browser launcher is not wired here.
        Subclasses or callers may override this behaviour.
        """
        logger.info("LiveTvLibrary.playChannelBrowser: vcn=%s (browser fallback not wired)", vcn)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _channel_by_vcn(self, vcn: str) -> Optional[LiveTvChannel]:
        """Return the channel with the given VCN, or None."""
        for ch in self._channels:
            if ch.vcn == vcn:
                return ch
        return None

    def _worker_refresh(self, client) -> None:
        """Worker thread: fetch HDHomeRun host and guide data."""
        try:
            # Step 1: get HDHomeRun host (skip if already known)
            if client is not None:
                host = self._fetch_hdhomerun_host(client)
                if host:
                    self._hdhomerun_host = host

            hdhomerun_host = self._hdhomerun_host
            if not hdhomerun_host:
                logger.warning("LiveTvLibrary: no HDHomeRun host found")
                self._loadingUpdate.emit(False)
                return

            # Step 2: warm start — serve cache immediately if available
            cached_channels = self._load_guide_cache(hdhomerun_host)
            if cached_channels:
                self._channels = cached_channels
                self._channelsReady.emit(cached_channels)
                self._loadingUpdate.emit(False)
                logger.info("LiveTvLibrary: served %d channels from cache", len(cached_channels))

            # Step 3: fetch fresh guide data (always, even on warm start)
            channels = self._fetch_and_build_channels(hdhomerun_host)
            if channels:
                self._save_guide_cache(channels)
                self._channels = channels
                self._channelsReady.emit(channels)
                if not cached_channels:
                    self._loadingUpdate.emit(False)
                logger.info("LiveTvLibrary: refreshed %d channels from HDHomeRun guide", len(channels))
            elif not cached_channels:
                self._loadingUpdate.emit(False)

        except Exception:  # noqa: BLE001
            logger.exception("LiveTvLibrary: error during refresh")
            self._loadingUpdate.emit(False)

    # ------------------------------------------------------------------
    # HDHomeRun host resolution (via Plex DVR)
    # ------------------------------------------------------------------

    def _fetch_hdhomerun_host(self, client) -> str:
        """Fetch /livetv/dvrs and extract the HDHomeRun host."""
        try:
            data = client._get("/livetv/dvrs")
            if data is None:
                return ""
            dvrs = data.get("MediaContainer", {}).get("Dvr", [])
            if not dvrs:
                return ""
            devices = dvrs[0].get("Device", [])
            if not devices:
                return ""
            uri = devices[0].get("uri", "")
            if not uri:
                return ""
            parsed = urlparse(uri)
            return parsed.hostname or ""
        except Exception:  # noqa: BLE001
            logger.warning("LiveTvLibrary: failed to fetch HDHomeRun host")
            return ""

    # ------------------------------------------------------------------
    # HDHomeRun device and guide API
    # ------------------------------------------------------------------

    def _fetch_device_auth(self, host: str) -> str:
        """GET http://{host}/discover.json — returns DeviceAuth token."""
        try:
            resp = requests.get(f"http://{host}/discover.json", timeout=5)
            resp.raise_for_status()
            return resp.json().get("DeviceAuth", "")
        except Exception:  # noqa: BLE001
            logger.warning("LiveTvLibrary: failed to fetch DeviceAuth from %s", host)
            return ""

    def _fetch_lineup(self, host: str) -> dict[str, dict]:
        """GET http://{host}/lineup.json — returns all tunable channels keyed by VCN."""
        try:
            resp = requests.get(f"http://{host}/lineup.json", timeout=5)
            resp.raise_for_status()
            channels = resp.json()
            return {ch["GuideNumber"]: ch for ch in channels if "GuideNumber" in ch}
        except Exception:  # noqa: BLE001
            logger.warning("LiveTvLibrary: failed to fetch lineup from %s", host)
            return {}

    def _fetch_guide_data(self, device_auth: str) -> list[dict]:
        """GET https://api.hdhomerun.com/api/guide — returns all channels with programs."""
        try:
            resp = requests.get(
                "https://api.hdhomerun.com/api/guide",
                params={"DeviceAuth": device_auth},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:  # noqa: BLE001
            logger.warning("LiveTvLibrary: failed to fetch HDHomeRun guide")
            return []

    def _fetch_and_build_channels(self, host: str) -> list[LiveTvChannel]:
        """Fetch lineup + guide from HDHomeRun and build channel list."""
        # Fetch auth first (fast, local), then lineup+guide in parallel
        device_auth = self._fetch_device_auth(host)

        with ThreadPoolExecutor(max_workers=2) as pool:
            lineup_future = pool.submit(self._fetch_lineup, host)
            guide_future = pool.submit(self._fetch_guide_data, device_auth) if device_auth else None

            lineup = lineup_future.result()
            guide_data = guide_future.result() if guide_future else []

        return self._build_channels_from_guide(guide_data, lineup, host)

    # ------------------------------------------------------------------
    # Channel building from HDHomeRun guide
    # ------------------------------------------------------------------

    def _build_channels_from_guide(
        self,
        guide_data: list[dict],
        lineup: dict[str, dict],
        host: str,
    ) -> list[LiveTvChannel]:
        """Build LiveTvChannel list from HDHomeRun guide API response.

        guide_data: list of channel dicts from api.hdhomerun.com/api/guide
        lineup: dict of VCN -> lineup entry from /lineup.json
        host: HDHomeRun IP address
        """
        now = int(time.time())
        channels: list[LiveTvChannel] = []
        guide_vcns: set[str] = set()

        for ch in guide_data:
            vcn = ch.get("GuideNumber", "")
            if not vcn:
                continue
            guide_vcns.add(vcn)

            guide_name = ch.get("GuideName", vcn)
            affiliate = ch.get("Affiliate", "")
            channel_thumb = ch.get("ImageURL", "")

            # Build title: "7.1 WKBWDT (ABC)" or "7.1 WKBWDT" if no affiliate
            if affiliate:
                title = f"{vcn} {guide_name} ({affiliate})"
            else:
                title = f"{vcn} {guide_name}"

            # Stream URL from lineup (authoritative) or constructed
            lineup_entry = lineup.get(vcn, {})
            stream_url = lineup_entry.get("URL", f"http://{host}:5004/auto/v{vcn}")

            # Find current and next programs
            programs = ch.get("Guide", [])
            programs_sorted = sorted(programs, key=lambda p: p.get("StartTime", 0))

            current_program = ""
            current_start = 0
            current_end = 0
            current_thumb = ""
            current_synopsis = ""
            next_program = ""
            next_start = 0
            next_end = 0
            next_thumb = ""
            next_synopsis = ""
            on_air = False

            for prog in programs_sorted:
                start = prog.get("StartTime", 0)
                end = prog.get("EndTime", 0)
                title_prog = prog.get("Title", "")
                synopsis = prog.get("Synopsis", "")
                prog_thumb = prog.get("ImageURL", "")

                if start <= now < end:
                    current_program = title_prog
                    current_start = start
                    current_end = end
                    current_thumb = prog_thumb
                    current_synopsis = synopsis
                    on_air = True
                elif start > now and not next_program:
                    next_program = title_prog
                    next_start = start
                    next_end = end
                    next_thumb = prog_thumb
                    next_synopsis = synopsis
                    break  # programs are sorted; first future one is next

            channels.append(LiveTvChannel(
                channel_id=0,
                vcn=vcn,
                title=title,
                call_sign=guide_name,
                thumb=channel_thumb,
                grid_key="",
                stream_url=stream_url,
                current_program=current_program,
                current_start=current_start,
                current_end=current_end,
                current_thumb=current_thumb,
                next_program=next_program,
                next_start=next_start,
                next_end=next_end,
                next_thumb=next_thumb,
                on_air=on_air,
                affiliate=affiliate,
                current_synopsis=current_synopsis,
                next_synopsis=next_synopsis,
            ))

        # Lineup-only channels (tunable but absent from the guide API) are intentionally
        # excluded — they have no programme data and would appear as blank rows in the UI.

        # Sort numerically by VCN
        def _vcn_sort_key(ch: LiveTvChannel) -> tuple:
            parts = ch.vcn.split(".")
            try:
                return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
            except ValueError:
                return (9999, 0)

        channels.sort(key=_vcn_sort_key)
        logger.info("LiveTvLibrary: built %d channels (%d with guide data)",
                    len(channels), len(guide_vcns))
        return channels

    # ------------------------------------------------------------------
    # Cache I/O
    # ------------------------------------------------------------------

    def _save_guide_cache(self, channels: list[LiveTvChannel]) -> None:
        """Serialize channels to guide_cache.json."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "vcn": ch.vcn,
                "title": ch.title,
                "call_sign": ch.call_sign,
                "affiliate": ch.affiliate,
                "thumb": ch.thumb,
                "stream_url": ch.stream_url,
                "current_program": ch.current_program,
                "current_start": ch.current_start,
                "current_end": ch.current_end,
                "current_thumb": ch.current_thumb,
                "current_synopsis": ch.current_synopsis,
                "next_program": ch.next_program,
                "next_start": ch.next_start,
                "next_end": ch.next_end,
                "next_thumb": ch.next_thumb,
                "next_synopsis": ch.next_synopsis,
                "on_air": ch.on_air,
            }
            for ch in channels
        ]
        path = _CACHE_DIR / "guide_cache.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    def _load_guide_cache(self, hdhomerun_host: str) -> list[LiveTvChannel]:
        """Load channels from guide_cache.json. Returns [] if missing or corrupt."""
        path = _CACHE_DIR / "guide_cache.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            channels = []
            for d in data:
                # Rebuild stream_url with current host in case IP changed
                vcn = d.get("vcn", "")
                stream_url = d.get("stream_url", "")
                if hdhomerun_host and vcn and not stream_url:
                    stream_url = f"http://{hdhomerun_host}:5004/auto/v{vcn}"
                channels.append(LiveTvChannel(
                    channel_id=0,
                    vcn=vcn,
                    title=d.get("title", ""),
                    call_sign=d.get("call_sign", ""),
                    thumb=d.get("thumb", ""),
                    grid_key="",
                    stream_url=stream_url,
                    current_program=d.get("current_program", ""),
                    current_start=d.get("current_start", 0),
                    current_end=d.get("current_end", 0),
                    current_thumb=d.get("current_thumb", ""),
                    next_program=d.get("next_program", ""),
                    next_start=d.get("next_start", 0),
                    next_end=d.get("next_end", 0),
                    next_thumb=d.get("next_thumb", ""),
                    on_air=d.get("on_air", False),
                    affiliate=d.get("affiliate", ""),
                    current_synopsis=d.get("current_synopsis", ""),
                    next_synopsis=d.get("next_synopsis", ""),
                ))
            return channels
        except (json.JSONDecodeError, OSError, KeyError):
            return []

    def _clear_cache(self) -> None:
        """Delete all files in _CACHE_DIR (does not delete the directory itself)."""
        if not _CACHE_DIR.exists():
            return
        for f in _CACHE_DIR.iterdir():
            if f.is_file():
                f.unlink()

    # ------------------------------------------------------------------
    # Signal handlers (main thread)
    # ------------------------------------------------------------------

    def _on_channels_ready(self, channels: list[LiveTvChannel]) -> None:
        """Handle channels ready signal on main thread."""
        self._channels_model.set_channels(channels)
        self._loading = False
        self.loadingChanged.emit(False)
        self.channelsChanged.emit()

    def shutdown(self) -> None:
        """Shut down the thread pool. Call on app exit."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _on_loading_update(self, loading: bool) -> None:
        """Handle loading state update on main thread."""
        self._loading = loading
        self.loadingChanged.emit(loading)
