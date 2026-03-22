"""Moonlight library manager for HTPC Station.

Exposes Moonlight streaming host and app data to QML via models and slots.
Host discovery and availability checks run off the main thread using a
ThreadPoolExecutor.  Models are updated on the main thread only.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from backend.moonlight_artwork import get_artwork_path, refresh_artwork
from backend.moonlight_client import MoonlightLauncher, list_apps
from backend.moonlight_models import MoonlightApp, MoonlightHost
from backend.moonlight_parser import check_host_available, discover_moonlight_hosts

logger = logging.getLogger(__name__)

# Default Moonlight command (Flatpak installation)
_DEFAULT_MOONLIGHT_COMMAND = "flatpak run com.moonlight_stream.Moonlight"


# ---------------------------------------------------------------------------
# MoonlightAppListModel
# ---------------------------------------------------------------------------


class MoonlightAppListModel(QAbstractListModel):
    """QAbstractListModel wrapping a list of :class:`MoonlightApp` objects.

    Roles: name (str), hostUuid (str), imagePath (str)
    """

    NameRole = Qt.ItemDataRole.UserRole + 1
    HostUuidRole = Qt.ItemDataRole.UserRole + 2
    ImagePathRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._apps: list[MoonlightApp] = []

    def set_apps(self, apps: list[MoonlightApp]) -> None:
        """Replace the model contents. Must be called on the main thread."""
        self.beginResetModel()
        self._apps = apps
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._apps)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._apps)):
            return None
        app = self._apps[index.row()]
        if role == self.NameRole:
            return app.name
        if role == self.HostUuidRole:
            return app.host_uuid
        if role == self.ImagePathRole:
            return app.image_path
        if role == Qt.ItemDataRole.DisplayRole:
            return app.name
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.NameRole: b"name",
            self.HostUuidRole: b"hostUuid",
            self.ImagePathRole: b"imagePath",
        }


# ---------------------------------------------------------------------------
# MoonlightLibrary — main orchestrator
# ---------------------------------------------------------------------------


class MoonlightLibrary(QObject):
    """Manages Moonlight streaming data and exposes it to QML.

    Exposed to QML as the ``moonlight`` context property.

    All host discovery and availability checks are dispatched to a
    ThreadPoolExecutor.  Results are delivered back to the main thread via
    Qt signals.

    Two-phase refresh:
        Phase 1 (fast): discover paired hosts from local files, emit hostsChanged
        Phase 2 (slow, threaded): TCP probe + app enumeration, emit hostsChanged again

    QML properties:
        appsModel — :class:`MoonlightAppListModel` (app grid)

    QML signals:
        appsModelChanged — emitted when the apps model is updated
        hostsChanged     — emitted after Phase 1 and Phase 2
        processStarted   — forwarded from MoonlightLauncher
        processFinished(exit_code, elapsed_seconds) — forwarded from MoonlightLauncher

    QML slots:
        refresh()                    — two-phase: discover hosts then enumerate apps
        getApp(index)                — return app details dict
        launchApp(hostAddress, appName) — launch a streaming session
        launchGui()                  — launch the Moonlight GUI
        getPairedHosts()             — return list of paired hosts for Settings selector
        setSelectedHost(uuid)        — change the selected host and re-refresh apps
        sortApps(sortKey)            — sort apps (az, za)
    """

    appsModelChanged = Signal()
    hostsChanged = Signal()
    loadingChanged = Signal()
    processStarted = Signal()
    processFinished = Signal(int, int)

    # Internal signals to marshal results from worker thread to main thread
    _hostsDiscovered = Signal(list)          # Phase 1: (paired_hosts,)
    _appsDone = Signal(list, dict)           # Phase 2: (apps, host_availability)

    def __init__(
        self,
        moonlight_command: str = _DEFAULT_MOONLIGHT_COMMAND,
        host_uuid: str = "",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self._moonlight_command = moonlight_command
        self._selected_host_uuid: str = host_uuid

        # Internal state
        self._paired_hosts: list[MoonlightHost] = []
        self._hosts: list[MoonlightHost] = []          # kept for getApp() host lookup
        self._host_availability: dict[str, bool] = {}
        self._all_apps: list[MoonlightApp] = []
        self._current_apps: list[MoonlightApp] = []
        self._current_host_uuid: str = ""              # kept for sortApps filter compat
        self._current_sort: str = "az"
        self._loading: bool = False

        # App list model
        self._apps_model = MoonlightAppListModel(self)

        # Launcher (must stay on main thread — uses QProcess)
        self._launcher = MoonlightLauncher(self)
        self._launcher.processStarted.connect(self.processStarted)
        self._launcher.processFinished.connect(self.processFinished)

        # Thread pool for blocking I/O (host probing + app listing)
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Connect internal signals (worker → main thread)
        self._hostsDiscovered.connect(self._on_hosts_discovered)
        self._appsDone.connect(self._on_apps_done)

    # ------------------------------------------------------------------
    # Q_PROPERTYs
    # ------------------------------------------------------------------

    appsModel = Property(
        QObject,
        fget=lambda self: self._apps_model,
        notify=appsModelChanged,
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
        """Two-phase refresh.

        Phase 1 (synchronous, fast): discover paired hosts from local files.
        Emits ``hostsChanged`` immediately so the source list appears right away.

        Phase 2 (threaded, slow): TCP probe + app enumeration for the selected
        host.  Emits ``hostsChanged`` again when apps are loaded.
        """
        # Set loading=True before Phase 1 so _on_moonlight_hosts_changed reads True
        self._loading = True
        self.loadingChanged.emit()

        # Phase 1: fast local file read — run synchronously on the main thread
        try:
            hosts = discover_moonlight_hosts()
        except Exception as exc:  # noqa: BLE001
            logger.warning("MoonlightLibrary: failed to discover hosts: %s", exc)
            hosts = []

        logger.info("MoonlightLibrary: discovered %d host(s)", len(hosts))

        if not hosts:
            # No paired hosts — Phase 2 will not run; clear loading state now
            self._loading = False
            self.loadingChanged.emit()

        # Deliver Phase 1 results on the main thread immediately
        self._hostsDiscovered.emit(hosts)

        # Phase 2: slow I/O — run on the thread pool
        self._executor.submit(self._worker_phase2, hosts)

    @Slot(int, result="QVariant")
    def getApp(self, index: int) -> dict:
        """Return a dict of all fields for the app at *index*.

        Returns an empty dict if the index is out of range.
        """
        if not (0 <= index < len(self._current_apps)):
            return {}
        app = self._current_apps[index]
        # Find the host for this app
        host = next((h for h in self._paired_hosts if h.uuid == app.host_uuid), None)
        return {
            "name": app.name,
            "hostAddress": host.address if host else "",
            "hostName": host.display_name if host else "",
            "hostUuid": app.host_uuid,
            "imagePath": app.image_path,
        }

    @Slot(str, str)
    def launchApp(self, host_address: str, app_name: str) -> None:
        """Launch a Moonlight streaming session for *app_name* on *host_address*."""
        if not host_address or not app_name:
            logger.warning(
                "MoonlightLibrary.launchApp: empty host_address or app_name — ignoring"
            )
            return
        logger.info(
            "MoonlightLibrary.launchApp: launching '%s' on %s", app_name, host_address
        )
        self._launcher.launch(host_address, app_name, self._moonlight_command)

    @Slot()
    def launchGui(self) -> None:
        """Launch the Moonlight GUI (for pairing / host management)."""
        logger.info("MoonlightLibrary.launchGui: launching Moonlight GUI")
        self._launcher.launch_gui(self._moonlight_command)

    @Slot(result="QVariant")
    def getPairedHosts(self) -> list:
        """Return a list of paired hosts for the Settings host selector.

        Returns ``[{"id": uuid, "label": "hostname (ip)"}]``.
        Called by SettingsManager.getHostsList().
        """
        result = []
        for host in self._paired_hosts:
            address = host.address or host.local_address or host.manual_address or ""
            label = f"{host.display_name} ({address})" if address else host.display_name
            result.append({"id": host.uuid, "label": label})
        return result

    @Slot(str)
    def setSelectedHost(self, uuid: str) -> None:
        """Change the selected host and trigger a re-refresh of apps.

        Called by SettingsManager when the user changes the host in Settings.
        """
        logger.info("MoonlightLibrary.setSelectedHost: selecting host %s", uuid)
        self._selected_host_uuid = uuid
        # Re-run Phase 2 with the new selected host
        self._executor.submit(self._worker_phase2, self._paired_hosts)

    @Slot(str)
    def selectHost(self, host_uuid: str) -> None:
        """Filter apps to show only apps from the selected host.

        Kept for backward compatibility with existing tests and QML.
        If *host_uuid* is empty, show all apps.
        """
        self._current_host_uuid = host_uuid
        self._apply_filter_and_sort()

    @Slot(str)
    def sortApps(self, sort_key: str) -> None:
        """Sort the apps model.

        sort_key: 'az' (A-Z), 'za' (Z-A).
        No 'recent' sort for Moonlight (no play timestamps).
        """
        self._current_sort = sort_key
        self._apply_filter_and_sort()

    # ------------------------------------------------------------------
    # Internal: worker thread function (Phase 2)
    # ------------------------------------------------------------------

    def _worker_phase2(self, hosts: list) -> None:
        """Worker: probe the selected host and enumerate its apps."""
        # Determine which host to use
        selected = None
        if self._selected_host_uuid:
            selected = next((h for h in hosts if h.uuid == self._selected_host_uuid), None)
        if selected is None and hosts:
            selected = hosts[0]

        if selected is None:
            logger.info("MoonlightLibrary: no host to probe — skipping Phase 2")
            self._appsDone.emit([], {})
            return

        address = selected.address or selected.local_address or selected.manual_address
        if not address:
            logger.info(
                "MoonlightLibrary: host %s has no address — skipping probe",
                selected.display_name,
            )
            self._appsDone.emit([], {selected.uuid: False})
            return

        # TCP probe
        available = check_host_available(address)
        host_availability = {selected.uuid: available}
        logger.debug(
            "MoonlightLibrary: host %s (%s) available=%s",
            selected.display_name,
            address,
            available,
        )

        # Enumerate apps if available
        all_apps: list[MoonlightApp] = []
        if available:
            try:
                app_names = list_apps(address, self._moonlight_command)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MoonlightLibrary: failed to list apps on %s: %s",
                    selected.display_name,
                    exc,
                )
                app_names = []

            for name in app_names:
                image_path = self._resolve_artwork(name)
                all_apps.append(
                    MoonlightApp(name=name, host_uuid=selected.uuid, image_path=image_path)
                )

        logger.info(
            "MoonlightLibrary: found %d app(s) on %s",
            len(all_apps),
            selected.display_name,
        )

        # Deliver Phase 2 results to main thread via signal
        self._appsDone.emit(all_apps, host_availability)

    # ------------------------------------------------------------------
    # Internal: main-thread result handlers
    # ------------------------------------------------------------------

    def _on_hosts_discovered(self, hosts: list) -> None:
        """Handle Phase 1 results on the main thread.

        Updates _paired_hosts, auto-selects a host if needed, and emits
        hostsChanged so the source list appears immediately (with 0 apps).
        """
        self._paired_hosts = hosts
        self._hosts = hosts  # keep _hosts in sync for getApp() lookups

        # Auto-select: if _selected_host_uuid is empty or not in paired hosts,
        # pick the first paired host.
        if hosts:
            uuids = {h.uuid for h in hosts}
            if not self._selected_host_uuid or self._selected_host_uuid not in uuids:
                self._selected_host_uuid = hosts[0].uuid
                logger.info(
                    "MoonlightLibrary: auto-selected host %s", self._selected_host_uuid
                )

        # Emit hostsChanged so main.py can show "Moonlight Games (0 apps)" immediately
        self.hostsChanged.emit()

    def _on_apps_done(self, apps: list, host_availability: dict) -> None:
        """Handle Phase 2 results on the main thread."""
        self._host_availability = host_availability
        self._all_apps = apps

        # Clear loading state BEFORE emitting hostsChanged so the final update
        # shows the real count (not "Loading...")
        self._loading = False
        self.loadingChanged.emit()

        # Emit hostsChanged so main.py updates the app count
        self.hostsChanged.emit()

        # Rebuild the filtered/sorted app list
        self._apply_filter_and_sort()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_artwork(self, app_name: str) -> str:
        """Return a local artwork path for *app_name*, downloading if needed.

        1. Calls ``get_artwork_path`` — returns immediately if cached.
        2. If None, calls ``refresh_artwork`` to download from Steam CDN.
        3. Returns the path as a string, or ``""`` on any failure.

        Safe to call from a worker thread.
        """
        try:
            path = get_artwork_path(app_name)
            if path is None:
                path = refresh_artwork(app_name)
            return str(path) if path is not None else ""
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "MoonlightLibrary: failed to resolve artwork for '%s': %s", app_name, exc
            )
            return ""

    def _apply_filter_and_sort(self) -> None:
        """Filter and sort ``_all_apps`` and push the result to ``_apps_model``."""
        apps = list(self._all_apps)

        # Filter by host if a specific host is selected (legacy selectHost support)
        if self._current_host_uuid:
            apps = [a for a in apps if a.host_uuid == self._current_host_uuid]

        # Sort
        if self._current_sort == "az":
            apps.sort(key=lambda a: a.name.lower())
        elif self._current_sort == "za":
            apps.sort(key=lambda a: a.name.lower(), reverse=True)
        else:
            logger.warning(
                "MoonlightLibrary._apply_filter_and_sort: unknown sort_key '%s'",
                self._current_sort,
            )
            apps.sort(key=lambda a: a.name.lower())

        self._current_apps = apps
        self._apps_model.set_apps(apps)
        self.appsModelChanged.emit()
