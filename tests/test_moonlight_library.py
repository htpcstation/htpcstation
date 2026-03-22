"""Tests for MoonlightLibrary QObject + PC Games Source List Integration.

Covers:
  - MoonlightAppListModel: roles, data, set_apps
  - MoonlightLibrary: construction, appsModel property
  - MoonlightLibrary.refresh: two-phase (Phase 1 sync, Phase 2 threaded)
  - MoonlightLibrary.getApp: valid index, out-of-range
  - MoonlightLibrary.launchApp: delegates to MoonlightLauncher
  - MoonlightLibrary.launchGui: delegates to MoonlightLauncher
  - MoonlightLibrary.getPairedHosts: returns correct format
  - MoonlightLibrary.setSelectedHost: triggers re-refresh
  - MoonlightLibrary.selectHost: filtering by host UUID (backward compat)
  - MoonlightLibrary.sortApps: az, za, unknown key
  - Auto-selection: first host selected when uuid empty or stale
  - SteamLibrary.setMoonlightSources: rebuilds sources model, emits signal
  - Artwork integration: cache hit, download, failure scenarios
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call, patch

import pytest
from PySide6.QtCore import QCoreApplication, QModelIndex, Qt

from backend.moonlight_models import MoonlightApp, MoonlightHost


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_host(
    name: str = "DESKTOP-PC",
    uuid: str = "uuid-1",
    address: str = "192.168.0.10",
    custom_name: str = "",
) -> MoonlightHost:
    return MoonlightHost(
        name=name,
        uuid=uuid,
        address=address,
        local_address="",
        remote_address="",
        manual_address="",
        mac_address="",
        custom_name=custom_name,
    )


def _make_app(name: str = "Desktop", host_uuid: str = "uuid-1") -> MoonlightApp:
    return MoonlightApp(name=name, host_uuid=host_uuid)


def _pump_events(timeout_ms: int = 2000) -> None:
    """Process Qt events for up to *timeout_ms* milliseconds.

    Polls processEvents() in a tight loop to deliver cross-thread signals.
    The timeout is generous to accommodate slow CI environments.
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)


# ---------------------------------------------------------------------------
# MoonlightAppListModel
# ---------------------------------------------------------------------------


class TestMoonlightAppListModel:
    def test_roles_and_data(self) -> None:
        """MoonlightAppListModel exposes name, hostUuid, and imagePath roles correctly."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        app = MoonlightApp(name="Cyberpunk 2077", host_uuid="uuid-abc", image_path="/art/cp.jpg")
        model.set_apps([app])

        assert model.rowCount() == 1
        idx = model.index(0, 0)
        assert model.data(idx, MoonlightAppListModel.NameRole) == "Cyberpunk 2077"
        assert model.data(idx, MoonlightAppListModel.HostUuidRole) == "uuid-abc"
        assert model.data(idx, MoonlightAppListModel.ImagePathRole) == "/art/cp.jpg"

    def test_role_names(self) -> None:
        """roleNames returns the expected byte-string keys."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        names = model.roleNames()
        assert b"name" in names.values()
        assert b"hostUuid" in names.values()
        assert b"imagePath" in names.values()

    def test_image_path_role_empty_by_default(self) -> None:
        """ImagePathRole returns empty string when image_path is not set."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        model.set_apps([_make_app("Desktop")])
        idx = model.index(0, 0)
        assert model.data(idx, MoonlightAppListModel.ImagePathRole) == ""

    def test_display_role_returns_name(self) -> None:
        """DisplayRole returns the app name."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        model.set_apps([_make_app("Desktop")])
        idx = model.index(0, 0)
        assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "Desktop"

    def test_invalid_index_returns_none(self) -> None:
        """data() returns None for an invalid QModelIndex."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        assert model.data(QModelIndex(), MoonlightAppListModel.NameRole) is None

    def test_out_of_range_index_returns_none(self) -> None:
        """data() returns None for an out-of-range row."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        model.set_apps([_make_app()])
        idx = model.index(99, 0)
        assert model.data(idx, MoonlightAppListModel.NameRole) is None

    def test_set_apps_replaces_contents(self) -> None:
        """set_apps() replaces the model contents."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        model.set_apps([_make_app("First")])
        assert model.rowCount() == 1

        model.set_apps([_make_app("Second"), _make_app("Third")])
        assert model.rowCount() == 2

    def test_parent_valid_returns_zero(self) -> None:
        """rowCount with a valid parent returns 0 (list model, not tree)."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        model.set_apps([_make_app()])
        parent = model.index(0, 0)
        assert model.rowCount(parent) == 0

    def test_unknown_role_returns_none(self) -> None:
        """data() returns None for an unknown role."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        model.set_apps([_make_app()])
        idx = model.index(0, 0)
        assert model.data(idx, 9999) is None

    def test_empty_model_row_count_zero(self) -> None:
        """An empty model has rowCount == 0."""
        from backend.moonlight_library import MoonlightAppListModel

        model = MoonlightAppListModel()
        assert model.rowCount() == 0


# ---------------------------------------------------------------------------
# MoonlightLibrary — construction and properties
# ---------------------------------------------------------------------------


class TestMoonlightLibraryConstruction:
    def test_apps_model_property_returns_model(self) -> None:
        """appsModel property returns a MoonlightAppListModel."""
        from backend.moonlight_library import MoonlightAppListModel, MoonlightLibrary

        lib = MoonlightLibrary()
        assert isinstance(lib.appsModel, MoonlightAppListModel)

    def test_initial_apps_model_is_empty(self) -> None:
        """appsModel starts empty (no refresh called)."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        assert lib.appsModel.rowCount() == 0

    def test_custom_moonlight_command_stored(self) -> None:
        """Constructor stores the moonlight_command."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary(moonlight_command="/usr/bin/moonlight")
        assert lib._moonlight_command == "/usr/bin/moonlight"

    def test_default_moonlight_command(self) -> None:
        """Default moonlight_command is the Flatpak command."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        assert "flatpak" in lib._moonlight_command.lower() or "moonlight" in lib._moonlight_command.lower()

    def test_initial_state_empty(self) -> None:
        """Internal state starts empty."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        assert lib._paired_hosts == []
        assert lib._host_availability == {}
        assert lib._all_apps == []
        assert lib._current_apps == []
        assert lib._current_host_uuid == ""

    def test_host_uuid_constructor_parameter(self) -> None:
        """Constructor stores the host_uuid parameter as _selected_host_uuid."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary(host_uuid="uuid-abc")
        assert lib._selected_host_uuid == "uuid-abc"

    def test_default_host_uuid_is_empty(self) -> None:
        """Default host_uuid is empty string."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        assert lib._selected_host_uuid == ""


# ---------------------------------------------------------------------------
# MoonlightLibrary — refresh (threaded)
# ---------------------------------------------------------------------------


class TestMoonlightLibraryRefresh:
    def _make_lib(self) -> "MoonlightLibrary":
        from backend.moonlight_library import MoonlightLibrary
        return MoonlightLibrary()

    def _refresh_and_wait(self, lib, patches: dict) -> None:
        """Helper: call refresh(), wait for both phases to finish, then pump events.

        Phase 1 (discover) runs synchronously on the main thread.
        Phase 2 (check + list_apps) runs on the thread pool.

        The patches must remain active while processEvents() is called because
        Qt delivers cross-thread signals synchronously during processEvents().
        We shut down the executor (blocking until the worker finishes) and then
        call processEvents() — all while the patches are still in effect.
        """
        from concurrent.futures import ThreadPoolExecutor

        with patch("backend.moonlight_library.discover_moonlight_hosts",
                   **patches.get("discover", {"return_value": []})), \
             patch("backend.moonlight_library.check_host_available",
                   **patches.get("check", {"return_value": False})), \
             patch("backend.moonlight_library.list_apps",
                   **patches.get("list_apps", {"return_value": []})), \
             patch("backend.moonlight_library.get_artwork_path",
                   **patches.get("get_artwork_path", {"return_value": None})), \
             patch("backend.moonlight_library.refresh_artwork",
                   **patches.get("refresh_artwork", {"return_value": None})):
            lib.refresh()
            # Phase 1 is synchronous — _hostsDiscovered signal is already queued.
            # Block until Phase 2 worker thread finishes (signal is now queued)
            lib._executor.shutdown(wait=True)
            # Deliver all queued cross-thread signals on the main thread
            QCoreApplication.processEvents()
            # Restore the executor for future calls
            lib._executor = ThreadPoolExecutor(max_workers=2)

    def test_refresh_discovers_hosts_and_apps(self) -> None:
        """refresh() populates _paired_hosts and _all_apps."""
        lib = self._make_lib()

        host = _make_host("DESKTOP-PC", "uuid-1", "192.168.0.10")
        apps_result = ["Cyberpunk 2077", "Desktop"]

        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"return_value": True},
            "list_apps": {"return_value": apps_result},
        })

        assert len(lib._paired_hosts) == 1
        assert lib._paired_hosts[0].uuid == "uuid-1"
        assert len(lib._all_apps) == 2
        assert {a.name for a in lib._all_apps} == {"Cyberpunk 2077", "Desktop"}

    def test_refresh_marks_unavailable_hosts(self) -> None:
        """refresh() marks hosts as unavailable when check_host_available returns False."""
        lib = self._make_lib()

        host = _make_host("OFFLINE-PC", "uuid-offline", "10.0.0.1")
        mock_list = MagicMock(return_value=[])

        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"return_value": False},
            "list_apps": {"side_effect": mock_list},
        })

        assert lib._host_availability.get("uuid-offline") is False
        # list_apps should NOT be called for unavailable hosts
        mock_list.assert_not_called()

    def test_refresh_no_hosts_results_in_empty_apps(self) -> None:
        """refresh() with no paired hosts results in empty apps model."""
        lib = self._make_lib()

        self._refresh_and_wait(lib, {
            "discover": {"return_value": []},
        })

        assert lib._all_apps == []
        assert lib.appsModel.rowCount() == 0

    def test_refresh_emits_hosts_changed(self) -> None:
        """refresh() emits hostsChanged after discovery completes."""
        lib = self._make_lib()

        signals: list[bool] = []
        lib.hostsChanged.connect(lambda: signals.append(True))

        self._refresh_and_wait(lib, {
            "discover": {"return_value": []},
        })

        assert len(signals) >= 1

    def test_refresh_emits_apps_model_changed(self) -> None:
        """refresh() emits appsModelChanged after apps are loaded."""
        lib = self._make_lib()

        signals: list[bool] = []
        lib.appsModelChanged.connect(lambda: signals.append(True))

        host = _make_host()
        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"return_value": True},
            "list_apps": {"return_value": ["Desktop"]},
        })

        assert len(signals) >= 1

    def test_refresh_updates_apps_model(self) -> None:
        """refresh() updates the appsModel with discovered apps."""
        from backend.moonlight_library import MoonlightAppListModel

        lib = self._make_lib()

        host = _make_host()
        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"return_value": True},
            "list_apps": {"return_value": ["Desktop", "Steam"]},
        })

        assert lib.appsModel.rowCount() == 2
        idx = lib.appsModel.index(0, 0)
        # After az sort, Desktop comes before Steam
        assert lib.appsModel.data(idx, MoonlightAppListModel.NameRole) == "Desktop"

    def test_refresh_multiple_hosts_discovers_all(self) -> None:
        """refresh() discovers all paired hosts in Phase 1."""
        lib = self._make_lib()

        host1 = _make_host("PC1", "uuid-1", "192.168.0.10")
        host2 = _make_host("PC2", "uuid-2", "192.168.0.11")

        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host1, host2]},
            "check": {"return_value": True},
            "list_apps": {"return_value": ["Game A"]},
        })

        # Both hosts are discovered in Phase 1
        assert len(lib._paired_hosts) == 2
        uuids = {h.uuid for h in lib._paired_hosts}
        assert uuids == {"uuid-1", "uuid-2"}

    def test_refresh_phase2_probes_selected_host_only(self) -> None:
        """Phase 2 probes only the selected host (first host when none selected)."""
        lib = self._make_lib()

        host1 = _make_host("PC1", "uuid-1", "192.168.0.10")
        host2 = _make_host("PC2", "uuid-2", "192.168.0.11")

        def _list_apps(address: str, cmd: str) -> list[str]:
            if address == "192.168.0.10":
                return ["Game A"]
            return ["Game B", "Game C"]

        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host1, host2]},
            "check": {"return_value": True},
            "list_apps": {"side_effect": _list_apps},
        })

        # Only the selected host's apps are loaded (first host auto-selected)
        assert lib._selected_host_uuid == "uuid-1"
        assert len(lib._all_apps) == 1
        assert lib._all_apps[0].name == "Game A"

    def test_refresh_handles_list_apps_exception(self) -> None:
        """refresh() handles exceptions from list_apps gracefully."""
        lib = self._make_lib()

        host = _make_host()
        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"return_value": True},
            "list_apps": {"side_effect": RuntimeError("oops")},
        })

        # Should not crash; apps should be empty
        assert lib._all_apps == []

    def test_refresh_handles_discover_exception(self) -> None:
        """refresh() handles exceptions from discover_moonlight_hosts gracefully."""
        lib = self._make_lib()

        self._refresh_and_wait(lib, {
            "discover": {"side_effect": OSError("no file")},
        })

        assert lib._paired_hosts == []
        assert lib._all_apps == []

    def test_refresh_uses_host_address_for_availability_check(self) -> None:
        """refresh() uses host.address for the availability probe."""
        lib = self._make_lib()

        host = _make_host(address="10.0.0.5")
        checked_addresses: list[str] = []

        def _check(address: str) -> bool:
            checked_addresses.append(address)
            return False

        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"side_effect": _check},
        })

        assert "10.0.0.5" in checked_addresses

    def test_refresh_falls_back_to_local_address(self) -> None:
        """refresh() falls back to local_address when address is empty."""
        lib = self._make_lib()

        host = MoonlightHost(
            name="PC",
            uuid="uuid-1",
            address="",
            local_address="192.168.1.5",
            remote_address="",
            manual_address="",
            mac_address="",
            custom_name="",
        )
        checked_addresses: list[str] = []

        def _check(address: str) -> bool:
            checked_addresses.append(address)
            return False

        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"side_effect": _check},
        })

        assert "192.168.1.5" in checked_addresses

    def test_refresh_phase1_emits_hosts_changed_immediately(self) -> None:
        """Phase 1 emits hostsChanged synchronously before Phase 2 completes."""
        from backend.moonlight_library import MoonlightLibrary
        from concurrent.futures import ThreadPoolExecutor

        lib = MoonlightLibrary()
        phase1_signals: list[bool] = []

        # We'll capture signals emitted during Phase 1 (before executor shuts down)
        lib.hostsChanged.connect(lambda: phase1_signals.append(True))

        host = _make_host("PC1", "uuid-1", "192.168.0.10")

        with patch("backend.moonlight_library.discover_moonlight_hosts",
                   return_value=[host]), \
             patch("backend.moonlight_library.check_host_available",
                   return_value=True), \
             patch("backend.moonlight_library.list_apps",
                   return_value=["Game A"]), \
             patch("backend.moonlight_library.get_artwork_path", return_value=None), \
             patch("backend.moonlight_library.refresh_artwork", return_value=None):
            lib.refresh()
            # After refresh() returns, Phase 1 signal should already be queued
            QCoreApplication.processEvents()
            # At least one hostsChanged from Phase 1
            assert len(phase1_signals) >= 1
            # Shut down Phase 2
            lib._executor.shutdown(wait=True)
            QCoreApplication.processEvents()
            lib._executor = ThreadPoolExecutor(max_workers=2)

        # After both phases, at least 2 hostsChanged signals
        assert len(phase1_signals) >= 2

    def test_auto_select_first_host_when_uuid_empty(self) -> None:
        """When host_uuid is empty, auto-select the first paired host."""
        lib = self._make_lib()  # no host_uuid

        host = _make_host("PC1", "uuid-1", "192.168.0.10")
        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"return_value": False},
        })

        assert lib._selected_host_uuid == "uuid-1"

    def test_auto_select_first_host_when_uuid_stale(self) -> None:
        """When host_uuid doesn't match any paired host, auto-select the first."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary(host_uuid="uuid-stale")

        host = _make_host("PC1", "uuid-1", "192.168.0.10")
        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"return_value": False},
        })

        assert lib._selected_host_uuid == "uuid-1"

    def test_no_auto_select_when_uuid_matches(self) -> None:
        """When host_uuid matches a paired host, keep it."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary(host_uuid="uuid-2")

        host1 = _make_host("PC1", "uuid-1", "192.168.0.10")
        host2 = _make_host("PC2", "uuid-2", "192.168.0.11")
        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host1, host2]},
            "check": {"return_value": False},
        })

        assert lib._selected_host_uuid == "uuid-2"


# ---------------------------------------------------------------------------
# MoonlightLibrary — getPairedHosts
# ---------------------------------------------------------------------------


class TestMoonlightLibraryGetPairedHosts:
    def test_returns_empty_before_refresh(self) -> None:
        """getPairedHosts returns [] before any refresh."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        assert lib.getPairedHosts() == []

    def test_returns_correct_format(self) -> None:
        """getPairedHosts returns [{"id": uuid, "label": "name (ip)"}]."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._paired_hosts = [_make_host("DESKTOP-PC", "uuid-1", "192.168.0.10")]

        result = lib.getPairedHosts()
        assert len(result) == 1
        assert result[0]["id"] == "uuid-1"
        assert result[0]["label"] == "DESKTOP-PC (192.168.0.10)"

    def test_uses_custom_name_in_label(self) -> None:
        """getPairedHosts uses display_name (custom_name if set) in label."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._paired_hosts = [_make_host("DESKTOP-PC", "uuid-1", "192.168.0.10", custom_name="My PC")]

        result = lib.getPairedHosts()
        assert result[0]["label"] == "My PC (192.168.0.10)"

    def test_label_without_address(self) -> None:
        """getPairedHosts uses just the name when no address is available."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._paired_hosts = [_make_host("DESKTOP-PC", "uuid-1", address="")]

        result = lib.getPairedHosts()
        assert result[0]["label"] == "DESKTOP-PC"

    def test_multiple_hosts(self) -> None:
        """getPairedHosts returns all paired hosts."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._paired_hosts = [
            _make_host("PC1", "uuid-1", "192.168.0.10"),
            _make_host("PC2", "uuid-2", "192.168.0.11"),
        ]

        result = lib.getPairedHosts()
        assert len(result) == 2
        ids = {r["id"] for r in result}
        assert ids == {"uuid-1", "uuid-2"}


# ---------------------------------------------------------------------------
# MoonlightLibrary — setSelectedHost
# ---------------------------------------------------------------------------


class TestMoonlightLibrarySetSelectedHost:
    def _make_lib_with_hosts(self) -> "MoonlightLibrary":
        from backend.moonlight_library import MoonlightLibrary
        from concurrent.futures import ThreadPoolExecutor

        lib = MoonlightLibrary()
        lib._paired_hosts = [
            _make_host("PC1", "uuid-1", "192.168.0.10"),
            _make_host("PC2", "uuid-2", "192.168.0.11"),
        ]
        return lib

    def test_set_selected_host_updates_uuid(self) -> None:
        """setSelectedHost updates _selected_host_uuid."""
        lib = self._make_lib_with_hosts()

        with patch("backend.moonlight_library.check_host_available", return_value=False), \
             patch("backend.moonlight_library.list_apps", return_value=[]), \
             patch("backend.moonlight_library.get_artwork_path", return_value=None), \
             patch("backend.moonlight_library.refresh_artwork", return_value=None):
            lib.setSelectedHost("uuid-2")
            lib._executor.shutdown(wait=True)
            QCoreApplication.processEvents()
            from concurrent.futures import ThreadPoolExecutor
            lib._executor = ThreadPoolExecutor(max_workers=2)

        assert lib._selected_host_uuid == "uuid-2"

    def test_set_selected_host_triggers_phase2(self) -> None:
        """setSelectedHost triggers Phase 2 to load apps for the new host."""
        from backend.moonlight_library import MoonlightLibrary
        from concurrent.futures import ThreadPoolExecutor

        lib = MoonlightLibrary()
        lib._paired_hosts = [
            _make_host("PC1", "uuid-1", "192.168.0.10"),
            _make_host("PC2", "uuid-2", "192.168.0.11"),
        ]

        def _list_apps(address: str, cmd: str) -> list[str]:
            if address == "192.168.0.11":
                return ["Game B"]
            return []

        with patch("backend.moonlight_library.check_host_available", return_value=True), \
             patch("backend.moonlight_library.list_apps", side_effect=_list_apps), \
             patch("backend.moonlight_library.get_artwork_path", return_value=None), \
             patch("backend.moonlight_library.refresh_artwork", return_value=None):
            lib.setSelectedHost("uuid-2")
            lib._executor.shutdown(wait=True)
            QCoreApplication.processEvents()
            lib._executor = ThreadPoolExecutor(max_workers=2)

        assert lib._selected_host_uuid == "uuid-2"
        assert len(lib._all_apps) == 1
        assert lib._all_apps[0].name == "Game B"

    def test_set_selected_host_emits_hosts_changed(self) -> None:
        """setSelectedHost emits hostsChanged after Phase 2 completes."""
        from backend.moonlight_library import MoonlightLibrary
        from concurrent.futures import ThreadPoolExecutor

        lib = MoonlightLibrary()
        lib._paired_hosts = [_make_host("PC1", "uuid-1", "192.168.0.10")]

        signals: list[bool] = []
        lib.hostsChanged.connect(lambda: signals.append(True))

        with patch("backend.moonlight_library.check_host_available", return_value=False), \
             patch("backend.moonlight_library.list_apps", return_value=[]), \
             patch("backend.moonlight_library.get_artwork_path", return_value=None), \
             patch("backend.moonlight_library.refresh_artwork", return_value=None):
            lib.setSelectedHost("uuid-1")
            lib._executor.shutdown(wait=True)
            QCoreApplication.processEvents()
            lib._executor = ThreadPoolExecutor(max_workers=2)

        assert len(signals) >= 1


# ---------------------------------------------------------------------------
# MoonlightLibrary — getApp
# ---------------------------------------------------------------------------


class TestMoonlightLibraryGetApp:
    def _make_lib_with_apps(self, apps: list[MoonlightApp], hosts: list[MoonlightHost] | None = None):
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._paired_hosts = hosts or []
        lib._hosts = hosts or []
        lib._all_apps = apps
        lib._current_apps = list(apps)
        lib._apps_model.set_apps(apps)
        return lib

    def test_get_app_returns_dict(self) -> None:
        """getApp returns a dict with name, hostAddress, hostName, hostUuid, imagePath."""
        host = _make_host("DESKTOP-PC", "uuid-1", "192.168.0.10")
        app = _make_app("Cyberpunk 2077", "uuid-1")
        lib = self._make_lib_with_apps([app], [host])

        result = lib.getApp(0)
        assert result["name"] == "Cyberpunk 2077"
        assert result["hostAddress"] == "192.168.0.10"
        assert result["hostName"] == "DESKTOP-PC"
        assert result["hostUuid"] == "uuid-1"
        assert result["imagePath"] == ""

    def test_get_app_returns_image_path(self) -> None:
        """getApp returns imagePath from the app's image_path field."""
        host = _make_host("DESKTOP-PC", "uuid-1", "192.168.0.10")
        app = MoonlightApp(name="Cyberpunk 2077", host_uuid="uuid-1", image_path="/art/cp.jpg")
        lib = self._make_lib_with_apps([app], [host])

        result = lib.getApp(0)
        assert result["imagePath"] == "/art/cp.jpg"

    def test_get_app_out_of_range_returns_empty(self) -> None:
        """getApp returns {} for out-of-range index."""
        lib = self._make_lib_with_apps([])
        assert lib.getApp(0) == {}
        assert lib.getApp(-1) == {}
        assert lib.getApp(99) == {}

    def test_get_app_unknown_host_returns_empty_strings(self) -> None:
        """getApp returns empty strings for hostAddress/hostName when host not found."""
        app = _make_app("Desktop", "uuid-unknown")
        lib = self._make_lib_with_apps([app], hosts=[])

        result = lib.getApp(0)
        assert result["name"] == "Desktop"
        assert result["hostAddress"] == ""
        assert result["hostName"] == ""
        assert result["hostUuid"] == "uuid-unknown"

    def test_get_app_uses_custom_name(self) -> None:
        """getApp uses host.display_name (custom_name if set)."""
        host = _make_host("DESKTOP-PC", "uuid-1", "192.168.0.10", custom_name="My Gaming PC")
        app = _make_app("Desktop", "uuid-1")
        lib = self._make_lib_with_apps([app], [host])

        result = lib.getApp(0)
        assert result["hostName"] == "My Gaming PC"

    def test_get_app_reflects_current_sort_order(self) -> None:
        """getApp returns the app at the sorted position."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._paired_hosts = [_make_host()]
        lib._all_apps = [_make_app("Zelda"), _make_app("Asteroids")]
        lib._apply_filter_and_sort()  # default az sort

        # After az sort: Asteroids first, Zelda second
        assert lib.getApp(0)["name"] == "Asteroids"
        assert lib.getApp(1)["name"] == "Zelda"


# ---------------------------------------------------------------------------
# MoonlightLibrary — launchApp
# ---------------------------------------------------------------------------


class TestMoonlightLibraryLaunchApp:
    def test_launch_app_delegates_to_launcher(self) -> None:
        """launchApp delegates to MoonlightLauncher.launch."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary(moonlight_command="/usr/bin/moonlight")
        mock_launch = MagicMock()
        lib._launcher.launch = mock_launch

        lib.launchApp("192.168.0.10", "Cyberpunk 2077")

        mock_launch.assert_called_once_with(
            "192.168.0.10", "Cyberpunk 2077", "/usr/bin/moonlight"
        )

    def test_launch_app_empty_host_is_noop(self) -> None:
        """launchApp with empty host_address does nothing."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        mock_launch = MagicMock()
        lib._launcher.launch = mock_launch

        lib.launchApp("", "Desktop")
        mock_launch.assert_not_called()

    def test_launch_app_empty_app_name_is_noop(self) -> None:
        """launchApp with empty app_name does nothing."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        mock_launch = MagicMock()
        lib._launcher.launch = mock_launch

        lib.launchApp("192.168.0.10", "")
        mock_launch.assert_not_called()

    def test_launch_app_passes_moonlight_command(self) -> None:
        """launchApp passes the configured moonlight_command to the launcher."""
        from backend.moonlight_library import MoonlightLibrary

        custom_cmd = "flatpak run com.moonlight_stream.Moonlight"
        lib = MoonlightLibrary(moonlight_command=custom_cmd)
        mock_launch = MagicMock()
        lib._launcher.launch = mock_launch

        lib.launchApp("10.0.0.1", "Desktop")

        _, _, cmd_arg = mock_launch.call_args[0]
        assert cmd_arg == custom_cmd


# ---------------------------------------------------------------------------
# MoonlightLibrary — launchGui
# ---------------------------------------------------------------------------


class TestMoonlightLibraryLaunchGui:
    def test_launch_gui_delegates_to_launcher(self) -> None:
        """launchGui delegates to MoonlightLauncher.launch_gui."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary(moonlight_command="/usr/bin/moonlight")
        mock_launch_gui = MagicMock()
        lib._launcher.launch_gui = mock_launch_gui

        lib.launchGui()

        mock_launch_gui.assert_called_once_with("/usr/bin/moonlight")

    def test_launch_gui_passes_moonlight_command(self) -> None:
        """launchGui passes the configured moonlight_command to the launcher."""
        from backend.moonlight_library import MoonlightLibrary

        custom_cmd = "flatpak run com.moonlight_stream.Moonlight"
        lib = MoonlightLibrary(moonlight_command=custom_cmd)
        mock_launch_gui = MagicMock()
        lib._launcher.launch_gui = mock_launch_gui

        lib.launchGui()

        cmd_arg = mock_launch_gui.call_args[0][0]
        assert cmd_arg == custom_cmd


# ---------------------------------------------------------------------------
# MoonlightLibrary — selectHost
# ---------------------------------------------------------------------------


class TestMoonlightLibrarySelectHost:
    def _make_lib_with_apps(self) -> "MoonlightLibrary":
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._paired_hosts = [
            _make_host("PC1", "uuid-1", "192.168.0.10"),
            _make_host("PC2", "uuid-2", "192.168.0.11"),
        ]
        lib._all_apps = [
            _make_app("Game A", "uuid-1"),
            _make_app("Game B", "uuid-1"),
            _make_app("Game C", "uuid-2"),
        ]
        lib._apply_filter_and_sort()
        return lib

    def test_select_host_filters_apps(self) -> None:
        """selectHost filters apps to only those from the selected host."""
        lib = self._make_lib_with_apps()
        lib.selectHost("uuid-1")

        assert lib.appsModel.rowCount() == 2
        names = {lib._current_apps[i].name for i in range(2)}
        assert names == {"Game A", "Game B"}

    def test_select_host_empty_shows_all(self) -> None:
        """selectHost('') shows all apps from all hosts."""
        lib = self._make_lib_with_apps()
        lib.selectHost("uuid-1")  # filter first
        lib.selectHost("")        # then clear filter

        assert lib.appsModel.rowCount() == 3

    def test_select_host_unknown_uuid_shows_empty(self) -> None:
        """selectHost with an unknown UUID shows no apps."""
        lib = self._make_lib_with_apps()
        lib.selectHost("uuid-nonexistent")

        assert lib.appsModel.rowCount() == 0

    def test_select_host_emits_apps_model_changed(self) -> None:
        """selectHost emits appsModelChanged."""
        lib = self._make_lib_with_apps()

        signals: list[bool] = []
        lib.appsModelChanged.connect(lambda: signals.append(True))
        lib.selectHost("uuid-1")

        assert len(signals) == 1

    def test_select_host_updates_current_host_uuid(self) -> None:
        """selectHost updates _current_host_uuid."""
        lib = self._make_lib_with_apps()
        lib.selectHost("uuid-2")
        assert lib._current_host_uuid == "uuid-2"


# ---------------------------------------------------------------------------
# MoonlightLibrary — sortApps
# ---------------------------------------------------------------------------


class TestMoonlightLibrarySortApps:
    def _make_lib_with_apps(self) -> "MoonlightLibrary":
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._all_apps = [
            _make_app("Zelda"),
            _make_app("Asteroids"),
            _make_app("Mario"),
        ]
        lib._apply_filter_and_sort()
        return lib

    def test_sort_az(self) -> None:
        """sortApps('az') sorts alphabetically ascending."""
        lib = self._make_lib_with_apps()
        lib.sortApps("az")
        names = [lib._current_apps[i].name for i in range(3)]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_sort_za(self) -> None:
        """sortApps('za') sorts alphabetically descending."""
        lib = self._make_lib_with_apps()
        lib.sortApps("za")
        names = [lib._current_apps[i].name for i in range(3)]
        assert names == ["Zelda", "Mario", "Asteroids"]

    def test_sort_unknown_key_falls_back_to_az(self) -> None:
        """sortApps with unknown key falls back to A-Z."""
        lib = self._make_lib_with_apps()
        lib.sortApps("unknown")
        names = [lib._current_apps[i].name for i in range(3)]
        assert names == ["Asteroids", "Mario", "Zelda"]

    def test_sort_emits_apps_model_changed(self) -> None:
        """sortApps emits appsModelChanged."""
        lib = self._make_lib_with_apps()
        signals: list[bool] = []
        lib.appsModelChanged.connect(lambda: signals.append(True))
        lib.sortApps("za")
        assert len(signals) == 1

    def test_sort_updates_apps_model(self) -> None:
        """sortApps updates the appsModel so QML sees the new order."""
        from backend.moonlight_library import MoonlightAppListModel

        lib = self._make_lib_with_apps()
        lib.sortApps("za")

        idx = lib.appsModel.index(0, 0)
        assert lib.appsModel.data(idx, MoonlightAppListModel.NameRole) == "Zelda"

    def test_sort_case_insensitive(self) -> None:
        """sortApps sorts case-insensitively."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._all_apps = [
            _make_app("zelda"),
            _make_app("Asteroids"),
            _make_app("mario"),
        ]
        lib.sortApps("az")
        names = [lib._current_apps[i].name for i in range(3)]
        assert names == ["Asteroids", "mario", "zelda"]

    def test_sort_preserves_host_filter(self) -> None:
        """sortApps re-applies the current host filter."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        lib._all_apps = [
            _make_app("Zelda", "uuid-1"),
            _make_app("Asteroids", "uuid-1"),
            _make_app("Mario", "uuid-2"),
        ]
        lib._current_host_uuid = "uuid-1"
        lib.sortApps("az")

        # Only uuid-1 apps, sorted az
        assert lib.appsModel.rowCount() == 2
        names = [lib._current_apps[i].name for i in range(2)]
        assert names == ["Asteroids", "Zelda"]


# ---------------------------------------------------------------------------
# SteamLibrary — setMoonlightSources
# ---------------------------------------------------------------------------


class TestSteamLibrarySetMoonlightSources:
    def _make_steam_lib(self):
        from backend.steam_library import SteamLibrary

        with patch("backend.steam_library.discover_steam_games", return_value=[]):
            return SteamLibrary()

    def test_set_moonlight_sources_appends_to_steam(self) -> None:
        """setMoonlightSources appends Moonlight entries after the Steam entry."""
        from backend.steam_library import SteamSourceListModel

        lib = self._make_steam_lib()
        sources = [
            {"name": "DESKTOP-PC", "gameCount": 5, "source": "moonlight:uuid-1"},
        ]
        lib.setMoonlightSources(sources)

        assert lib._sources_model.rowCount() == 2
        idx0 = lib._sources_model.index(0, 0)
        idx1 = lib._sources_model.index(1, 0)
        assert lib._sources_model.data(idx0, SteamSourceListModel.NameRole) == "Steam"
        assert lib._sources_model.data(idx1, SteamSourceListModel.NameRole) == "DESKTOP-PC"
        assert lib._sources_model.data(idx1, SteamSourceListModel.SourceRole) == "moonlight:uuid-1"
        assert lib._sources_model.data(idx1, SteamSourceListModel.GameCountRole) == 5

    def test_set_moonlight_sources_empty_list_shows_only_steam(self) -> None:
        """setMoonlightSources([]) shows only the Steam entry."""
        from backend.steam_library import SteamSourceListModel

        lib = self._make_steam_lib()
        lib.setMoonlightSources([])

        assert lib._sources_model.rowCount() == 1
        idx = lib._sources_model.index(0, 0)
        assert lib._sources_model.data(idx, SteamSourceListModel.NameRole) == "Steam"

    def test_set_moonlight_sources_emits_sources_model_changed(self) -> None:
        """setMoonlightSources emits sourcesModelChanged."""
        lib = self._make_steam_lib()

        signals: list[bool] = []
        lib.sourcesModelChanged.connect(lambda: signals.append(True))
        lib.setMoonlightSources([])

        assert len(signals) == 1

    def test_set_moonlight_sources_multiple_hosts(self) -> None:
        """setMoonlightSources handles multiple Moonlight hosts."""
        from backend.steam_library import SteamSourceListModel

        lib = self._make_steam_lib()
        sources = [
            {"name": "PC1", "gameCount": 3, "source": "moonlight:uuid-1"},
            {"name": "PC2", "gameCount": 7, "source": "moonlight:uuid-2"},
        ]
        lib.setMoonlightSources(sources)

        assert lib._sources_model.rowCount() == 3  # Steam + 2 Moonlight

    def test_set_moonlight_sources_replaces_previous(self) -> None:
        """setMoonlightSources replaces previously injected Moonlight sources."""
        lib = self._make_steam_lib()

        lib.setMoonlightSources([
            {"name": "PC1", "gameCount": 3, "source": "moonlight:uuid-1"},
        ])
        assert lib._sources_model.rowCount() == 2

        # Replace with a different set
        lib.setMoonlightSources([
            {"name": "PC2", "gameCount": 5, "source": "moonlight:uuid-2"},
            {"name": "PC3", "gameCount": 2, "source": "moonlight:uuid-3"},
        ])
        assert lib._sources_model.rowCount() == 3  # Steam + 2 new Moonlight

    def test_set_moonlight_sources_steam_game_count_reflects_all_games(self) -> None:
        """setMoonlightSources preserves the correct Steam game count."""
        from backend.steam_library import SteamGame, SteamLibrary, SteamSourceListModel

        games = [
            SteamGame("1", "Game A", "gamea", 0, 0, ""),
            SteamGame("2", "Game B", "gameb", 0, 0, ""),
        ]
        with patch("backend.steam_library.discover_steam_games", return_value=games):
            lib = SteamLibrary()

        lib.setMoonlightSources([
            {"name": "PC1", "gameCount": 5, "source": "moonlight:uuid-1"},
        ])

        idx = lib._sources_model.index(0, 0)
        assert lib._sources_model.data(idx, SteamSourceListModel.GameCountRole) == 2


# ---------------------------------------------------------------------------
# MoonlightLibrary — signal forwarding
# ---------------------------------------------------------------------------


class TestMoonlightLibrarySignalForwarding:
    def test_process_started_forwarded(self) -> None:
        """processStarted signal is forwarded from MoonlightLauncher."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        received: list[bool] = []
        lib.processStarted.connect(lambda: received.append(True))

        lib._launcher.processStarted.emit()

        assert received == [True]

    def test_process_finished_forwarded(self) -> None:
        """processFinished signal is forwarded from MoonlightLauncher."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()
        received: list[tuple] = []
        lib.processFinished.connect(lambda code, elapsed: received.append((code, elapsed)))

        lib._launcher.processFinished.emit(0, 42)

        assert received == [(0, 42)]


# ---------------------------------------------------------------------------
# MoonlightLibrary — loading property
# ---------------------------------------------------------------------------


class TestMoonlightLibraryLoading:
    def _make_lib(self) -> "MoonlightLibrary":
        from backend.moonlight_library import MoonlightLibrary
        return MoonlightLibrary()

    def _refresh_and_wait(self, lib, patches: dict) -> None:
        """Helper: call refresh(), wait for both phases to finish, then pump events."""
        from concurrent.futures import ThreadPoolExecutor

        with patch("backend.moonlight_library.discover_moonlight_hosts",
                   **patches.get("discover", {"return_value": []})), \
             patch("backend.moonlight_library.check_host_available",
                   **patches.get("check", {"return_value": False})), \
             patch("backend.moonlight_library.list_apps",
                   **patches.get("list_apps", {"return_value": []})), \
             patch("backend.moonlight_library.get_artwork_path",
                   **patches.get("get_artwork_path", {"return_value": None})), \
             patch("backend.moonlight_library.refresh_artwork",
                   **patches.get("refresh_artwork", {"return_value": None})):
            lib.refresh()
            lib._executor.shutdown(wait=True)
            QCoreApplication.processEvents()
            lib._executor = ThreadPoolExecutor(max_workers=2)

    def test_loading_starts_false(self) -> None:
        """loading property is False before any refresh."""
        lib = self._make_lib()
        assert lib.loading is False

    def test_loading_true_during_phase1_with_hosts(self) -> None:
        """loading is True after Phase 1 emits hostsChanged (when hosts are found)."""
        from backend.moonlight_library import MoonlightLibrary
        from concurrent.futures import ThreadPoolExecutor

        lib = MoonlightLibrary()
        loading_states: list[bool] = []

        # Capture loading state at the time hostsChanged fires
        lib.hostsChanged.connect(lambda: loading_states.append(lib.loading))

        host = _make_host("PC1", "uuid-1", "192.168.0.10")

        with patch("backend.moonlight_library.discover_moonlight_hosts",
                   return_value=[host]), \
             patch("backend.moonlight_library.check_host_available",
                   return_value=True), \
             patch("backend.moonlight_library.list_apps",
                   return_value=["Game A"]), \
             patch("backend.moonlight_library.get_artwork_path", return_value=None), \
             patch("backend.moonlight_library.refresh_artwork", return_value=None):
            lib.refresh()
            # Process Phase 1 signal
            QCoreApplication.processEvents()
            # Phase 1 hostsChanged should have fired with loading=True
            assert len(loading_states) >= 1
            assert loading_states[0] is True

            # Wait for Phase 2 to complete
            lib._executor.shutdown(wait=True)
            QCoreApplication.processEvents()
            lib._executor = ThreadPoolExecutor(max_workers=2)

        # After Phase 2, loading should be False
        assert lib.loading is False

    def test_loading_false_after_phase2_completes(self) -> None:
        """loading is False after Phase 2 completes."""
        lib = self._make_lib()

        host = _make_host("PC1", "uuid-1", "192.168.0.10")
        self._refresh_and_wait(lib, {
            "discover": {"return_value": [host]},
            "check": {"return_value": True},
            "list_apps": {"return_value": ["Game A"]},
        })

        assert lib.loading is False

    def test_loading_false_when_no_hosts(self) -> None:
        """loading stays False (or returns to False) when no hosts are paired."""
        lib = self._make_lib()

        self._refresh_and_wait(lib, {
            "discover": {"return_value": []},
        })

        assert lib.loading is False

    def test_loading_emits_loading_changed(self) -> None:
        """loadingChanged is emitted when loading state changes."""
        from backend.moonlight_library import MoonlightLibrary
        from concurrent.futures import ThreadPoolExecutor

        lib = MoonlightLibrary()
        signals: list[bool] = []
        lib.loadingChanged.connect(lambda: signals.append(lib.loading))

        host = _make_host("PC1", "uuid-1", "192.168.0.10")

        with patch("backend.moonlight_library.discover_moonlight_hosts",
                   return_value=[host]), \
             patch("backend.moonlight_library.check_host_available",
                   return_value=True), \
             patch("backend.moonlight_library.list_apps",
                   return_value=["Game A"]), \
             patch("backend.moonlight_library.get_artwork_path", return_value=None), \
             patch("backend.moonlight_library.refresh_artwork", return_value=None):
            lib.refresh()
            lib._executor.shutdown(wait=True)
            QCoreApplication.processEvents()
            lib._executor = ThreadPoolExecutor(max_workers=2)

        # loadingChanged should have been emitted at least twice:
        # once True (start of refresh) and once False (end of Phase 2)
        assert len(signals) >= 2
        assert signals[0] is True   # first emission: loading=True
        assert signals[-1] is False  # last emission: loading=False

    def test_loading_false_in_final_hosts_changed(self) -> None:
        """loading is False when the final hostsChanged fires after Phase 2."""
        from backend.moonlight_library import MoonlightLibrary
        from concurrent.futures import ThreadPoolExecutor

        lib = MoonlightLibrary()
        loading_states: list[bool] = []
        lib.hostsChanged.connect(lambda: loading_states.append(lib.loading))

        host = _make_host("PC1", "uuid-1", "192.168.0.10")

        with patch("backend.moonlight_library.discover_moonlight_hosts",
                   return_value=[host]), \
             patch("backend.moonlight_library.check_host_available",
                   return_value=True), \
             patch("backend.moonlight_library.list_apps",
                   return_value=["Game A"]), \
             patch("backend.moonlight_library.get_artwork_path", return_value=None), \
             patch("backend.moonlight_library.refresh_artwork", return_value=None):
            lib.refresh()
            lib._executor.shutdown(wait=True)
            QCoreApplication.processEvents()
            lib._executor = ThreadPoolExecutor(max_workers=2)

        # The last hostsChanged should have loading=False
        assert len(loading_states) >= 2
        assert loading_states[-1] is False


# ---------------------------------------------------------------------------
# MoonlightLibrary — artwork integration
# ---------------------------------------------------------------------------


class TestMoonlightLibraryArtworkIntegration:
    """Tests for artwork resolution during Phase 2 refresh.

    All three scenarios from the Task Brief:
      Case 1: get_artwork_path returns a path → refresh_artwork not called
      Case 2: get_artwork_path returns None, refresh_artwork returns path
      Case 3: both raise exceptions / return None → image_path remains ""
    """

    def _refresh_and_wait_with_artwork(
        self,
        lib,
        app_names: list[str],
        get_artwork_path_mock,
        refresh_artwork_mock,
    ) -> None:
        """Run a full Phase 2 refresh with controlled artwork mocks."""
        from concurrent.futures import ThreadPoolExecutor

        host = _make_host("PC1", "uuid-1", "192.168.0.10")
        lib._paired_hosts = [host]

        with patch("backend.moonlight_library.discover_moonlight_hosts",
                   return_value=[host]), \
             patch("backend.moonlight_library.check_host_available",
                   return_value=True), \
             patch("backend.moonlight_library.list_apps",
                   return_value=app_names), \
             patch("backend.moonlight_library.get_artwork_path",
                   side_effect=get_artwork_path_mock), \
             patch("backend.moonlight_library.refresh_artwork",
                   side_effect=refresh_artwork_mock):
            lib.refresh()
            lib._executor.shutdown(wait=True)
            QCoreApplication.processEvents()
            lib._executor = ThreadPoolExecutor(max_workers=2)

    def test_cache_hit_skips_refresh_artwork(self) -> None:
        """Case 1: get_artwork_path returns a path → refresh_artwork is never called."""
        from backend.moonlight_library import MoonlightLibrary
        from pathlib import Path

        lib = MoonlightLibrary()
        cached_path = Path("/cache/cyberpunk.jpg")

        get_artwork_calls: list[str] = []
        refresh_artwork_calls: list[str] = []

        def _get_artwork(name: str):
            get_artwork_calls.append(name)
            return cached_path

        def _refresh_artwork(name: str):
            refresh_artwork_calls.append(name)
            return None

        self._refresh_and_wait_with_artwork(
            lib, ["Cyberpunk 2077"], _get_artwork, _refresh_artwork
        )

        assert len(lib._all_apps) == 1
        assert lib._all_apps[0].image_path == str(cached_path)
        assert "Cyberpunk 2077" in get_artwork_calls
        # refresh_artwork must NOT be called when get_artwork_path returns a path
        assert refresh_artwork_calls == []

    def test_cache_miss_calls_refresh_artwork(self) -> None:
        """Case 2: get_artwork_path returns None → refresh_artwork is called and path used."""
        from backend.moonlight_library import MoonlightLibrary
        from pathlib import Path

        lib = MoonlightLibrary()
        downloaded_path = Path("/cache/desktop.jpg")

        def _get_artwork(name: str):
            return None  # cache miss

        refresh_artwork_calls: list[str] = []

        def _refresh_artwork(name: str):
            refresh_artwork_calls.append(name)
            return downloaded_path

        self._refresh_and_wait_with_artwork(
            lib, ["Desktop"], _get_artwork, _refresh_artwork
        )

        assert len(lib._all_apps) == 1
        assert lib._all_apps[0].image_path == str(downloaded_path)
        assert "Desktop" in refresh_artwork_calls

    def test_artwork_failure_leaves_image_path_empty(self) -> None:
        """Case 3: both get_artwork_path and refresh_artwork fail → image_path is ''."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()

        def _get_artwork(name: str):
            raise OSError("disk error")

        def _refresh_artwork(name: str):
            raise RuntimeError("network error")

        self._refresh_and_wait_with_artwork(
            lib, ["Some Game"], _get_artwork, _refresh_artwork
        )

        assert len(lib._all_apps) == 1
        assert lib._all_apps[0].image_path == ""

    def test_artwork_both_return_none_leaves_image_path_empty(self) -> None:
        """Case 3 (None variant): both return None → image_path is ''."""
        from backend.moonlight_library import MoonlightLibrary

        lib = MoonlightLibrary()

        self._refresh_and_wait_with_artwork(
            lib,
            ["Unknown Game"],
            lambda name: None,
            lambda name: None,
        )

        assert len(lib._all_apps) == 1
        assert lib._all_apps[0].image_path == ""

    def test_image_path_stored_on_moonlight_app(self) -> None:
        """image_path is stored on the MoonlightApp object after Phase 2."""
        from backend.moonlight_library import MoonlightLibrary
        from pathlib import Path

        lib = MoonlightLibrary()
        art_path = Path("/art/game.png")

        self._refresh_and_wait_with_artwork(
            lib,
            ["My Game"],
            lambda name: art_path,
            lambda name: None,
        )

        assert lib._all_apps[0].image_path == str(art_path)

    def test_image_path_exposed_via_model_role(self) -> None:
        """ImagePathRole in the model returns the artwork path set on the app."""
        from backend.moonlight_library import MoonlightAppListModel
        from pathlib import Path

        model = MoonlightAppListModel()
        app = MoonlightApp(name="Game", host_uuid="uuid-1", image_path="/art/game.jpg")
        model.set_apps([app])

        idx = model.index(0, 0)
        assert model.data(idx, MoonlightAppListModel.ImagePathRole) == "/art/game.jpg"

    def test_multiple_apps_each_get_artwork(self) -> None:
        """Each app in the list gets its own artwork resolved independently."""
        from backend.moonlight_library import MoonlightLibrary
        from pathlib import Path

        lib = MoonlightLibrary()

        artwork_map = {
            "Game A": Path("/art/game-a.jpg"),
            "Game B": None,
        }

        def _get_artwork(name: str):
            return artwork_map.get(name)

        def _refresh_artwork(name: str):
            return None  # Game B has no artwork

        self._refresh_and_wait_with_artwork(
            lib, ["Game A", "Game B"], _get_artwork, _refresh_artwork
        )

        assert len(lib._all_apps) == 2
        apps_by_name = {a.name: a for a in lib._all_apps}
        assert apps_by_name["Game A"].image_path == str(Path("/art/game-a.jpg"))
        assert apps_by_name["Game B"].image_path == ""
