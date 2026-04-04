"""Live TV library manager for HTPC Station.

Fetches EPG data from the Plex EPG API and HDHomeRun device info,
then exposes a channel guide model to QML.
All network calls happen off the main thread using a ThreadPoolExecutor.
Models are updated on the main thread only.

Per-channel EPG schedules are cached to disk so the guide can be served
instantly on warm start, then refreshed in the background.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

from backend.config import CONFIG_DIR
from backend.live_tv_models import LiveTvChannel
from backend.mpv_launcher import MpvLauncher

logger = logging.getLogger(__name__)

_EPG_PAGE_SIZE = 100
_CACHE_DIR = CONFIG_DIR / "livetv_cache"


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

    @Slot()
    def forceRefresh(self) -> None:
        """Clear EPG cache and re-fetch everything."""
        self._clear_cache()
        self.refresh()

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
            # ── Step 1: resolve EPG key and HDHomeRun host ──────────────────
            epg_key, hdhomerun_host = self._resolve_epg_config(client)
            if not epg_key:
                self._loadingUpdate.emit(False)
                return

            self._epg_provider_key = epg_key
            self._hdhomerun_host = hdhomerun_host

            # ── Step 2: load from cache if available ────────────────────────
            channel_metas = self._load_channel_cache()
            if channel_metas:
                # Warm start: serve cached data immediately
                cached_channels = self._build_channels_from_cache(
                    channel_metas, hdhomerun_host
                )
                self._channels = cached_channels
                self._channelsReady.emit(cached_channels)
                self._loadingUpdate.emit(False)
                logger.info("LiveTvLibrary: served %d channels from cache", len(cached_channels))
            else:
                # Cold start: need channel list first
                channel_metas = self._fetch_and_cache_channel_list(client, epg_key, hdhomerun_host)
                if not channel_metas:
                    self._loadingUpdate.emit(False)
                    return

            # ── Step 3: refresh per-channel schedules in parallel ───────────
            # (runs after cache serve on warm start, or after channel list fetch on cold)
            self._refresh_channel_schedules(client, epg_key, channel_metas, hdhomerun_host)

        except Exception:  # noqa: BLE001
            logger.exception("LiveTvLibrary: error during refresh")
            self._loadingUpdate.emit(False)

    # ------------------------------------------------------------------
    # EPG config resolution
    # ------------------------------------------------------------------

    def _resolve_epg_config(self, client) -> tuple[str, str]:
        """Fetch EPG key and HDHomeRun host. Returns (epg_key, hdhomerun_host)."""
        epg_key = self._fetch_epg_provider_key(client)
        if not epg_key:
            logger.warning("LiveTvLibrary: could not find EPG provider key")
            return "", ""
        hdhomerun_host = self._fetch_hdhomerun_host(client)
        return epg_key, hdhomerun_host

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

    # ------------------------------------------------------------------
    # Hub on-air fetch
    # ------------------------------------------------------------------

    def _fetch_on_air_programs(self, client, epg_provider_key: str) -> dict[str, dict]:
        """Fetch currently-airing programs from the hubs/discover endpoint.

        Returns a dict keyed by channelVcn -> program item dict.
        One request, all channels, always current.
        """
        data = client._get(
            f"/{epg_provider_key}/hubs/discover",
            params={"promoted": "1", "includeTypeFirst": "1", "count": "100"},
        )
        if data is None:
            return {}
        hubs = data.get("MediaContainer", {}).get("Hub", [])
        if not hubs:
            return {}
        # First hub is "Shows On Now"
        items = hubs[0].get("Metadata", [])
        result: dict[str, dict] = {}
        for item in items:
            media = item.get("Media", [{}])[0]
            vcn = media.get("channelVcn", "")
            if vcn and vcn not in result:
                result[vcn] = item
        logger.info("LiveTvLibrary: fetched %d on-air programs from hub", len(result))
        return result

    # ------------------------------------------------------------------
    # Per-channel fetch
    # ------------------------------------------------------------------

    def _fetch_channel_programs(
        self,
        client,
        epg_provider_key: str,
        grid_key: str,
    ) -> list[dict]:
        """Fetch full program schedule for one channel via channelGridKey filter.

        No time params — returns the complete schedule including currently-airing program.
        """
        data = client._get(
            f"/{epg_provider_key}/grid",
            params={"type": "1", "channelGridKey": grid_key},
        )
        if data is None:
            return []
        return data.get("MediaContainer", {}).get("Metadata", [])

    # ------------------------------------------------------------------
    # Channel discovery (cold start)
    # ------------------------------------------------------------------

    def _fetch_and_cache_channel_list(
        self,
        client,
        epg_key: str,
        hdhomerun_host: str,
    ) -> list[dict]:
        """Discover channels via the full grid fetch and cache the channel list.

        Uses the existing speculative parallel page approach to get all items,
        then extracts unique channel metadata and saves channels.json.
        Returns the list of channel meta dicts.
        """
        now = int(time.time())
        grid_start = now - 1800
        grid_end = now + 7200

        base_params = {
            "type": "1",
            "gridStartTime": grid_start,
            "gridEndTime": grid_end,
            "X-Plex-Container-Size": _EPG_PAGE_SIZE,
        }

        def fetch_page(start: int) -> tuple[list[dict], int]:
            """Fetch one page; return (items, totalSize)."""
            params = {**base_params, "X-Plex-Container-Start": start}
            data = client._get(f"/{epg_key}/grid", params=params)
            if data is None:
                return [], 0
            container = data.get("MediaContainer", {})
            items = container.get("Metadata", [])
            total = int(container.get("totalSize", container.get("size", 0)))
            return items, total

        _MAX_PAGES = 10  # safety cap — 10 × 100 = 1000 items max
        speculative_starts = list(range(0, _MAX_PAGES * _EPG_PAGE_SIZE, _EPG_PAGE_SIZE))

        all_items: list[dict] = []
        total_size = 0

        with ThreadPoolExecutor(max_workers=len(speculative_starts)) as pool:
            futures: dict = {
                pool.submit(fetch_page, start): start
                for start in speculative_starts
            }
            results: dict[int, list[dict]] = {}
            for future in as_completed(futures):
                start = futures[future]
                try:
                    items, page_total = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("LiveTvLibrary: page fetch failed at %d: %s", start, exc)
                    continue
                if page_total > 0:
                    total_size = page_total
                results[start] = items

        # Assemble pages in order, stopping at totalSize
        for start in sorted(results):
            if total_size > 0 and start >= total_size:
                break
            all_items.extend(results[start])
            if not results[start] or len(results[start]) < _EPG_PAGE_SIZE:
                break

        if not all_items:
            return []

        logger.info("LiveTvLibrary: discovery fetched %d raw EPG items (totalSize=%d)",
                    len(all_items), total_size)

        # Extract unique channel metadata from items
        seen: dict[str, dict] = {}
        for item in all_items:
            media_list = item.get("Media", [])
            if not media_list:
                continue
            media = media_list[0]
            channel_id_str = media.get("channelIdentifier", "") or media.get("channelVcn", "")
            if not channel_id_str or channel_id_str in seen:
                continue
            seen[channel_id_str] = {
                "grid_key": media.get("gridKey", ""),
                "channel_identifier": channel_id_str,
                "vcn": str(media.get("channelVcn", "")),
                "channel_title": media.get("channelTitle", ""),
                "channel_thumb": media.get("channelThumb", ""),
                "channel_id": int(media.get("channelID", 0) or 0),
                "hdhomerun_host": hdhomerun_host,
            }

        channel_metas = list(seen.values())
        self._save_channel_cache(channel_metas)
        return channel_metas

    # ------------------------------------------------------------------
    # Per-channel schedule refresh
    # ------------------------------------------------------------------

    def _refresh_channel_schedules(
        self,
        client,
        epg_key: str,
        channel_metas: list[dict],
        hdhomerun_host: str,
    ) -> None:
        """Fetch per-channel programs in parallel, save cache, build channels, emit signal."""
        grid_keys = [m["grid_key"] for m in channel_metas]

        def fetch_and_cache(grid_key: str) -> tuple[str, list[dict]]:
            items = self._fetch_channel_programs(client, epg_key, grid_key)
            if items:
                self._save_channel_programs(grid_key, items)
            return grid_key, items

        # Fetch on-air hub + all per-channel grids in parallel
        all_programs: dict[str, list[dict]] = {}
        on_air_by_vcn: dict[str, dict] = {}

        with ThreadPoolExecutor(max_workers=max(len(grid_keys) + 1, 1)) as pool:
            hub_future = pool.submit(self._fetch_on_air_programs, client, epg_key)
            channel_futures = {
                pool.submit(fetch_and_cache, gk): gk
                for gk in grid_keys
            }

            try:
                on_air_by_vcn = hub_future.result()
                self._save_on_air(on_air_by_vcn)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LiveTvLibrary: hub fetch failed: %s", exc)

            for future in as_completed(channel_futures):
                try:
                    gk, items = future.result()
                    all_programs[gk] = items
                except Exception as exc:  # noqa: BLE001
                    logger.warning("LiveTvLibrary: schedule fetch failed: %s", exc)

        # Build channels from fresh data
        all_items: list[dict] = []
        for items in all_programs.values():
            all_items.extend(items)

        now = int(time.time())
        channels = self._build_channels(all_items, hdhomerun_host, now, on_air_by_vcn)
        self._channels = channels
        self._channelsReady.emit(channels)
        logger.info("LiveTvLibrary: refreshed %d channels from per-channel fetch", len(channels))

    # ------------------------------------------------------------------
    # Cache: build channels from cached data
    # ------------------------------------------------------------------

    def _build_channels_from_cache(
        self,
        channel_metas: list[dict],
        hdhomerun_host: str,
    ) -> list[LiveTvChannel]:
        """Load per-channel program files and build channels."""
        all_items: list[dict] = []
        for meta in channel_metas:
            items = self._load_channel_programs(meta["grid_key"])
            all_items.extend(items)
        on_air_by_vcn = self._load_on_air()
        now = int(time.time())
        return self._build_channels(all_items, hdhomerun_host, now, on_air_by_vcn)

    # ------------------------------------------------------------------
    # Cache I/O
    # ------------------------------------------------------------------

    def _save_channel_cache(self, channel_metas: list[dict]) -> None:
        """Write channels.json to _CACHE_DIR."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / "channels.json"
        path.write_text(json.dumps(channel_metas, indent=2), encoding="utf-8")

    def _load_channel_cache(self) -> list[dict]:
        """Read channels.json. Returns [] if missing or corrupt."""
        path = _CACHE_DIR / "channels.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_channel_programs(self, grid_key: str, items: list[dict]) -> None:
        """Write {grid_key}.json to _CACHE_DIR."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"{grid_key}.json"
        path.write_text(json.dumps(items), encoding="utf-8")

    def _load_channel_programs(self, grid_key: str) -> list[dict]:
        """Read {grid_key}.json. Returns [] if missing or corrupt."""
        path = _CACHE_DIR / f"{grid_key}.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_on_air(self, on_air: dict[str, dict]) -> None:
        """Write on_air.json to _CACHE_DIR."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / "on_air.json"
        path.write_text(json.dumps(on_air), encoding="utf-8")

    def _load_on_air(self) -> dict[str, dict]:
        """Read on_air.json. Returns {} if missing or corrupt."""
        path = _CACHE_DIR / "on_air.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _clear_cache(self) -> None:
        """Delete all files in _CACHE_DIR (does not delete the directory itself)."""
        if not _CACHE_DIR.exists():
            return
        for f in _CACHE_DIR.iterdir():
            if f.is_file():
                f.unlink()

    # ------------------------------------------------------------------
    # Channel building (unchanged)
    # ------------------------------------------------------------------

    def _build_channels(
        self,
        items: list[dict],
        hdhomerun_host: str,
        now: int,
        on_air_by_vcn: dict[str, dict] | None = None,
    ) -> list[LiveTvChannel]:
        """Build LiveTvChannel list from EPG grid items.

        Groups programs by channelIdentifier, then assigns current/next program.
        When *on_air_by_vcn* is provided (from hubs/discover), hub data takes
        priority over grid ``onAir`` flags for current program detection.
        Hub-only channels (VCNs in hub but not in grid) are added as minimal entries.
        The final list is sorted numerically by VCN.
        """
        logger.info("LiveTvLibrary: _build_channels received %d raw items", len(items))

        on_air_by_vcn = on_air_by_vcn or {}

        # Group programs by channelIdentifier (fall back to channelVcn if missing)
        channel_programs: dict[str, list[dict]] = {}
        channel_meta: dict[str, dict] = {}

        for item in items:
            media_list = item.get("Media", [])
            if not media_list:
                continue
            media = media_list[0]
            channel_id_str = media.get("channelIdentifier", "") or media.get("channelVcn", "")
            if not channel_id_str:
                continue

            if channel_id_str not in channel_programs:
                channel_programs[channel_id_str] = []
                channel_meta[channel_id_str] = media

            channel_programs[channel_id_str].append(item)

        logger.info("LiveTvLibrary: grouped into %d unique channelIdentifiers", len(channel_programs))

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

            current_program = ""
            current_start = 0
            current_end = 0
            current_thumb = ""
            next_program = ""
            next_start = 0
            next_end = 0
            next_thumb = ""
            on_air = False

            # Check hub data first (authoritative source for currently-airing programs)
            hub_item = on_air_by_vcn.get(vcn)
            if hub_item:
                hub_media = hub_item.get("Media", [{}])[0]
                current_program = hub_item.get("title", "")
                current_start = 0   # timestamps unreliable for display
                current_end = 0
                current_thumb = hub_item.get("thumb", "")
                on_air = True
                # Find next program from grid data: first program with beginsAt > hub beginsAt
                hub_begins = int(hub_media.get("beginsAt", 0) or 0)
                for prog in programs_sorted:
                    prog_media = prog.get("Media", [{}])[0]
                    begins_at = int(prog_media.get("beginsAt", 0) or 0)
                    if begins_at > hub_begins:
                        next_program = prog.get("title", "")
                        next_start = 0
                        next_end = 0
                        next_thumb = prog.get("thumb", "")
                        break
            else:
                # Fallback: use existing onAir flag logic
                for prog in programs_sorted:
                    prog_media = prog.get("Media", [{}])[0]
                    begins_at = int(prog_media.get("beginsAt", 0) or 0)
                    ends_at   = int(prog_media.get("endsAt",   0) or 0)
                    prog_on_air = bool(prog_media.get("onAir", False))
                    prog_title = prog.get("title", "")
                    prog_thumb = prog.get("thumb", "")

                    is_current = prog_on_air or (
                        ends_at > begins_at > 0
                        and begins_at <= now < ends_at
                    )

                    if is_current and not on_air:
                        current_program = prog_title
                        current_start = 0   # timestamps unreliable for display
                        current_end = 0
                        current_thumb = prog_thumb
                        on_air = True
                    elif not is_current and not next_program:
                        if on_air or begins_at > now:
                            next_program = prog_title
                            next_start = 0
                            next_end = 0
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

        # Channels in hub but not in grid — create minimal entries
        grid_vcns = {ch.vcn for ch in channels}
        for vcn, hub_item in on_air_by_vcn.items():
            if vcn in grid_vcns:
                continue
            hub_media = hub_item.get("Media", [{}])[0]
            stream_url = f"http://{hdhomerun_host}:5004/auto/v{vcn}" if hdhomerun_host and vcn else ""
            channels.append(LiveTvChannel(
                channel_id=int(hub_media.get("channelID", 0) or 0),
                vcn=vcn,
                title=hub_media.get("channelTitle", vcn),
                call_sign=hub_media.get("channelCallSign", vcn),
                thumb=hub_media.get("channelThumb", ""),
                grid_key=hub_media.get("gridKey", ""),
                stream_url=stream_url,
                current_program=hub_item.get("title", ""),
                current_start=0,
                current_end=0,
                current_thumb=hub_item.get("thumb", ""),
                next_program="",
                next_start=0,
                next_end=0,
                next_thumb="",
                on_air=True,
            ))

        # Sort channels numerically by VCN
        def _vcn_sort_key(ch: LiveTvChannel) -> tuple:
            parts = ch.vcn.split(".")
            try:
                return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
            except ValueError:
                return (9999, 0)

        channels.sort(key=_vcn_sort_key)

        return channels

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
