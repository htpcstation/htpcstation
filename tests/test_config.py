"""Tests for Task 001 — Expand SYSTEM_DEFAULTS in config.py.

Covers:
  - All new keys are present in SYSTEM_DEFAULTS.
  - Alias test: pcengine and pce both map to "PC Engine / TurboGrafx-16".
  - Alias test: wswan and wonderswan both use the same core.
  - Systems with empty core (wiiu, switch, ps3, psvita, xbox, xbox360) have core == "".
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import SYSTEM_DEFAULTS, Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> Config:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        return Config()


# ---------------------------------------------------------------------------
# SYSTEM_DEFAULTS — new keys present
# ---------------------------------------------------------------------------


class TestSystemDefaultsNewKeys:
    """Assert that all new keys added in Task 001 are present in SYSTEM_DEFAULTS."""

    # Knulli alternate folder names
    @pytest.mark.parametrize("key", ["pcengine", "pcenginecd", "wswan", "wswanc"])
    def test_knulli_alternate_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Nintendo
    @pytest.mark.parametrize("key", [
        "fds", "satellaview", "sufami", "snes-msu1", "sgb",
        "gb2players", "gbc2players", "n64dd", "n3ds", "gamecube",
        "wii", "wiiu", "switch", "virtualboy", "gameandwatch",
        "pokemini", "supergrafx",
    ])
    def test_nintendo_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Sega
    @pytest.mark.parametrize("key", [
        "sg1000", "pico", "msu-md", "saturn", "dreamcast",
        "naomi", "naomi2", "atomiswave", "megaduck",
    ])
    def test_sega_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Sony
    @pytest.mark.parametrize("key", ["ps2", "psp", "ps3", "psvita"])
    def test_sony_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Microsoft
    @pytest.mark.parametrize("key", ["xbox", "xbox360"])
    def test_microsoft_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Atari
    @pytest.mark.parametrize("key", [
        "atari5200", "atari800", "atarilynx", "lynx",
        "atarist", "xegs", "jaguar", "jaguarcd",
    ])
    def test_atari_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # SNK
    @pytest.mark.parametrize("key", ["neogeo", "neogeocd"])
    def test_snk_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Arcade
    @pytest.mark.parametrize("key", ["mame", "fbneo", "daphne"])
    def test_arcade_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Commodore
    @pytest.mark.parametrize("key", [
        "c64", "c128", "c20", "cplus4", "pet",
        "amiga500", "amiga1200", "amigacd32", "amigacdtv",
    ])
    def test_commodore_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Sinclair / Amstrad
    @pytest.mark.parametrize("key", ["zxspectrum", "zx81", "amstradcpc", "gx4000"])
    def test_sinclair_amstrad_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Apple
    @pytest.mark.parametrize("key", ["apple2", "apple2gs", "macintosh"])
    def test_apple_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # NEC
    @pytest.mark.parametrize("key", ["pc88", "pc98"])
    def test_nec_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Sharp
    @pytest.mark.parametrize("key", ["x68000", "x1"])
    def test_sharp_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Fujitsu
    @pytest.mark.parametrize("key", ["fm7", "fmtowns"])
    def test_fujitsu_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # MSX
    @pytest.mark.parametrize("key", ["msx1", "msx2", "msx2+", "msxturbor", "spectravideo"])
    def test_msx_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Mattel / Coleco / Magnavox
    @pytest.mark.parametrize("key", ["intellivision", "colecovision", "o2em", "videopacplus"])
    def test_mattel_coleco_magnavox_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Philips
    def test_cdi_present(self) -> None:
        assert "cdi" in SYSTEM_DEFAULTS

    # Acorn
    @pytest.mark.parametrize("key", ["bbc", "electron", "archimedes", "atom"])
    def test_acorn_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Texas Instruments / Tandy / Other home computers
    @pytest.mark.parametrize("key", ["ti99", "coco", "thomson", "dos", "scummvm"])
    def test_home_computer_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Handheld / portable
    @pytest.mark.parametrize("key", [
        "supervision", "lcdgames", "gamecom", "gmaster", "gamate",
        "gamepock", "gp32", "arduboy", "uzebox", "lowresnx",
        "tic80", "pico8", "commanderx16",
    ])
    def test_handheld_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"

    # Obscure / regional systems
    @pytest.mark.parametrize("key", [
        "adam", "advision", "apfm1000", "arcadia", "astrocde",
        "camplynx", "channelf", "crvision", "laser310", "multivision",
        "pv1000", "samcoupe", "scv", "socrates", "supracan",
        "tutor", "vc4000", "vectrex", "vsmile",
    ])
    def test_obscure_regional_keys_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# SYSTEM_DEFAULTS — original 20 keys still present and unchanged
# ---------------------------------------------------------------------------


class TestSystemDefaultsOriginalKeys:
    @pytest.mark.parametrize("key", [
        "gb", "gbc", "gba", "nes", "snes", "n64", "nds",
        "megadrive", "sega32x", "segacd", "mastersystem", "gamegear",
        "psx", "pce", "ngp", "ngpc", "atari2600", "atari7800",
        "wonderswan", "wonderswancolor",
    ])
    def test_original_key_present(self, key: str) -> None:
        assert key in SYSTEM_DEFAULTS, f"Original key missing: {key}"


# ---------------------------------------------------------------------------
# Alias tests via get_system
# ---------------------------------------------------------------------------


class TestGetSystemAliases:
    def test_pcengine_and_pce_same_display_name(self, tmp_path: Path) -> None:
        """get_system('pcengine') and get_system('pce') both return 'PC Engine / TurboGrafx-16'."""
        config = _make_config(tmp_path)
        assert config.get_system("pcengine").display_name == "PC Engine / TurboGrafx-16"
        assert config.get_system("pce").display_name == "PC Engine / TurboGrafx-16"

    def test_wswan_and_wonderswan_same_core(self, tmp_path: Path) -> None:
        """get_system('wswan') and get_system('wonderswan') both use the same core."""
        config = _make_config(tmp_path)
        assert config.get_system("wswan").core == config.get_system("wonderswan").core


# ---------------------------------------------------------------------------
# Systems with empty core
# ---------------------------------------------------------------------------


class TestEmptyCoreSystemsViaGetSystem:
    @pytest.mark.parametrize("key", ["wiiu", "switch", "ps3", "psvita", "xbox", "xbox360"])
    def test_empty_core_system(self, key: str, tmp_path: Path) -> None:
        """Systems without a libretro core should have core == ''."""
        config = _make_config(tmp_path)
        assert config.get_system(key).core == "", f"Expected empty core for {key}"


class TestEmptyCoreSystemsInDefaults:
    @pytest.mark.parametrize("key", ["wiiu", "switch", "ps3", "psvita", "xbox", "xbox360"])
    def test_empty_core_in_defaults(self, key: str) -> None:
        """SYSTEM_DEFAULTS entries for unsupported systems have core == ''."""
        assert SYSTEM_DEFAULTS[key]["core"] == "", f"Expected empty core for {key}"
