"""Live TV library manager for HTPC Station.

Fetches EPG data from the Plex EPG API and HDHomeRun device info,
then exposes a channel guide model to QML.
All network calls happen off the main thread using a ThreadPoolExecutor.
Models are updated on the main thread only.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional
from urllib.parse import urlparse

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from backend.live_tv_models import LiveTvChannel
from backend.mpv_launcher import MpvLauncher

logger = logging.getLogger(__name__)

_EPG_PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# LiveTvChannelModel
# ---------------------------------------------------------------------------


class LiveTvChannelModel(QAbstractListModel):
    """QML model for Live TV channels.

    Roles: channelId, vcn, title, callSign, thumb, streamUrl,
           currentProgram, currentStart, currentEnd, currentThumb,
           nextProgram, nextStart, nextEnd, nextThumb, onAir
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
        }


# ---------------------------------------------------------------------------
# LiveTvLibrary
# ---------------------------------------------------------------------------


class LiveTvLibrary(QObject):
    """Manages Live TV EPG data and exposes it to QML.

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
        self._epg_provider_key: str = ""
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
        """Fetch EPG provider key, HDHomeRun host, channels, and programs."""
        client = self._plex_client_factory()
        if client is None:
            logger.info("LiveTvLibrary.refresh: no Plex client configured")
            return
        self._loadingUpdate.emit(True)
        self._executor.submit(self._worker_refresh, client)

    @Slot(str)
    def playChannel(self, vcn: str) -> None:
        """Launch MPV with the HDHomeRun direct stream for the given channel VCN."""
        if not self._hdhomerun_host:
            logger.warning("LiveTvLibrary.playChannel: no HDHomeRun host available")
            return
        stream_url = f"http://{self._hdhomerun_host}:5004/auto/v{vcn}"
        channel = self._channel_by_vcn(vcn)
        title = channel.title if channel is not None else vcn
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
        """Worker thread: fetch EPG provider key, DVR host, and channel grid."""
        try:
            # Step 1: fetch EPG provider key
            epg_provider_key = self._fetch_epg_provider_key(client)
            if not epg_provider_key:
                logger.warning("LiveTvLibrary: could not find EPG provider key")
                self._loadingUpdate.emit(False)
                return

            # Step 2: fetch HDHomeRun host
            hdhomerun_host = self._fetch_hdhomerun_host(client)
            # hdhomerun_host may be "" — channels will have empty stream_url

            # Step 3: fetch all channels + programs from EPG grid
            channels = self._fetch_channels(client, epg_provider_key, hdhomerun_host)

            # Store state for playChannel()
            self._epg_provider_key = epg_provider_key
            self._hdhomerun_host = hdhomerun_host
            self._channels = channels

            self._channelsReady.emit(channels)
        except Exception:  # noqa: BLE001
            logger.exception("LiveTvLibrary: error during refresh")
            self._loadingUpdate.emit(False)

    def _fetch_epg_provider_key(self, client) -> str:
        """Fetch /media/providers and find the EPG cloud provider key."""
        data = client._get("/media/providers")
        if data is None:
            return ""
        providers = data.get("MediaContainer", {}).get("MediaProvider", [])
        for provider in providers:
            identifier = provider.get("identifier", "")
            if identifier.startswith("tv.plex.providers.epg.cloud"):
                return identifier
        return ""

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

    def _fetch_channels(
        self,
        client,
        epg_provider_key: str,
        hdhomerun_host: str,
    ) -> list[LiveTvChannel]:
        """Fetch all channels and programs from the EPG grid (paginated)."""
        now = int(time.time())
        grid_end = now + 10800  # 3 hours

        all_items: list[dict] = []
        start = 0

        while True:
            params = {
                "type": "1",
                "gridStartTime": now,
                "gridEndTime": grid_end,
                "X-Plex-Container-Start": start,
                "X-Plex-Container-Size": _EPG_PAGE_SIZE,
            }
            data = client._get(f"/{epg_provider_key}/grid", params=params)
            if data is None:
                break
            container = data.get("MediaContainer", {})
            items = container.get("Metadata", [])
            if not items:
                break
            all_items.extend(items)
            total_size = int(container.get("totalSize", container.get("size", 0)))
            start += len(items)
            if start >= total_size or len(items) < _EPG_PAGE_SIZE:
                break

        return self._build_channels(all_items, hdhomerun_host, now)

    def _build_channels(
        self,
        items: list[dict],
        hdhomerun_host: str,
        now: int,
    ) -> list[LiveTvChannel]:
        """Build LiveTvChannel list from EPG grid items.

        Groups programs by channelIdentifier, then assigns current/next program
        based on timestamps and the onAir flag.
        """
        # Group programs by channelIdentifier
        channel_programs: dict[str, list[dict]] = {}
        channel_meta: dict[str, dict] = {}

        for item in items:
            media_list = item.get("Media", [])
            if not media_list:
                continue
            media = media_list[0]
            channel_id_str = media.get("channelIdentifier", "")
            if not channel_id_str:
                continue

            if channel_id_str not in channel_programs:
                channel_programs[channel_id_str] = []
                channel_meta[channel_id_str] = media

            channel_programs[channel_id_str].append(item)

        channels: list[LiveTvChannel] = []

        for channel_id_str, programs in channel_programs.items():
            meta = channel_meta[channel_id_str]

            vcn = str(meta.get("channelVcn", ""))
            channel_title = meta.get("channelTitle", "")
            call_sign = meta.get("channelTitle", "")  # channelTitle is the call sign
            channel_thumb = meta.get("channelThumb", "")
            grid_key = meta.get("gridKey", "")
            channel_id = int(meta.get("channelID", 0) or 0)

            # Sort programs by beginsAt
            programs_sorted = sorted(
                programs,
                key=lambda p: int(p.get("Media", [{}])[0].get("beginsAt", 0) or 0),
            )

            # Find current and next programs
            current_program = ""
            current_start = 0
            current_end = 0
            current_thumb = ""
            next_program = ""
            next_start = 0
            next_end = 0
            next_thumb = ""
            on_air = False

            for prog in programs_sorted:
                prog_media = prog.get("Media", [{}])[0]
                begins_at = int(prog_media.get("beginsAt", 0) or 0)
                ends_at = int(prog_media.get("endsAt", 0) or 0)
                prog_on_air = bool(prog_media.get("onAir", False))
                prog_title = prog.get("title", "")
                prog_thumb = prog.get("thumb", "")

                is_current = begins_at <= now < ends_at

                if is_current or prog_on_air:
                    current_program = prog_title
                    current_start = begins_at
                    current_end = ends_at
                    current_thumb = prog_thumb
                    on_air = True
                elif begins_at > now and not next_program:
                    # First program that starts after now is the "next" program
                    next_program = prog_title
                    next_start = begins_at
                    next_end = ends_at
                    next_thumb = prog_thumb

            # Build stream URL
            stream_url = ""
            if hdhomerun_host and vcn:
                stream_url = f"http://{hdhomerun_host}:5004/auto/v{vcn}"

            channels.append(LiveTvChannel(
                channel_id=channel_id,
                vcn=vcn,
                title=channel_title,
                call_sign=call_sign,
                thumb=channel_thumb,
                grid_key=grid_key,
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
            ))

        return channels

    def _on_channels_ready(self, channels: list[LiveTvChannel]) -> None:
        """Handle channels ready signal on main thread."""
        self._channels_model.set_channels(channels)
        self._loading = False
        self.loadingChanged.emit(False)
        self.channelsChanged.emit()

    def _on_loading_update(self, loading: bool) -> None:
        """Handle loading state update on main thread."""
        self._loading = loading
        self.loadingChanged.emit(loading)
