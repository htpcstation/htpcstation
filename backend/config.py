"""Configuration management for HTPC Station.

Loads and saves a JSON config file at ~/.config/htpcstation/config.json.
Ships built-in defaults for ~190 retro systems using Knulli/Batocera folder naming.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "htpcstation"
CONFIG_FILE = CONFIG_DIR / "config.json"

_DEFAULT_RETROARCH_COMMAND = "flatpak run org.libretro.RetroArch"
_DEFAULT_CORES_DIRECTORY = "~/.var/app/org.libretro.RetroArch/config/retroarch/cores"
_DEFAULT_BROWSER_COMMAND = "flatpak run com.brave.Browser"
_DEFAULT_MOONLIGHT_COMMAND = "flatpak run com.moonlight_stream.Moonlight"

SYSTEM_DEFAULTS: dict[str, dict] = {
    # ── Already present (do not change) ──────────────────────────────────────
    "gb":              {"display_name": "Game Boy",                        "core": "gambatte_libretro.so",              "extensions": [".gb"]},
    "gbc":             {"display_name": "Game Boy Color",                  "core": "gambatte_libretro.so",              "extensions": [".gbc"]},
    "gba":             {"display_name": "Game Boy Advance",                "core": "gpsp_libretro.so",                  "extensions": [".gba"]},
    "nes":             {"display_name": "Nintendo Entertainment System",   "core": "mesen_libretro.so",                 "extensions": [".nes"]},
    "snes":            {"display_name": "Super Nintendo",                  "core": "snes9x_libretro.so",                "extensions": [".smc", ".sfc"]},
    "n64":             {"display_name": "Nintendo 64",                     "core": "mupen64plus_next_libretro.so",      "extensions": [".n64", ".z64", ".v64"]},
    "nds":             {"display_name": "Nintendo DS",                     "core": "melonds_libretro.so",               "extensions": [".nds"]},
    "megadrive":       {"display_name": "Sega Genesis / Mega Drive",       "core": "genesis_plus_gx_libretro.so",       "extensions": [".md", ".bin", ".gen"]},
    "sega32x":         {"display_name": "Sega 32X",                        "core": "picodrive_libretro.so",             "extensions": [".32x"]},
    "segacd":          {"display_name": "Sega CD",                         "core": "genesis_plus_gx_libretro.so",       "extensions": [".chd", ".cue"]},
    "mastersystem":    {"display_name": "Sega Master System",              "core": "genesis_plus_gx_libretro.so",       "extensions": [".sms"]},
    "gamegear":        {"display_name": "Sega Game Gear",                  "core": "genesis_plus_gx_libretro.so",       "extensions": [".gg"]},
    "psx":             {"display_name": "PlayStation",                     "core": "mednafen_psx_hw_libretro.so",       "extensions": [".chd", ".cue", ".pbp"]},
    "pce":             {"display_name": "PC Engine / TurboGrafx-16",       "core": "mednafen_pce_libretro.so",          "extensions": [".pce"]},
    "ngp":             {"display_name": "Neo Geo Pocket",                  "core": "mednafen_ngp_libretro.so",          "extensions": [".ngp"]},
    "ngpc":            {"display_name": "Neo Geo Pocket Color",            "core": "mednafen_ngp_libretro.so",          "extensions": [".ngc", ".ngp"]},
    "atari2600":       {"display_name": "Atari 2600",                      "core": "stella_libretro.so",                "extensions": [".a26"]},
    "atari7800":       {"display_name": "Atari 7800",                      "core": "prosystem_libretro.so",             "extensions": [".a78"]},
    "wonderswan":      {"display_name": "WonderSwan",                      "core": "mednafen_wswan_libretro.so",        "extensions": [".ws"]},
    "wonderswancolor": {"display_name": "WonderSwan Color",                "core": "mednafen_wswan_libretro.so",        "extensions": [".wsc"]},

    # ── Knulli alternate folder names for existing systems ────────────────────
    "pcengine":        {"display_name": "PC Engine / TurboGrafx-16",       "core": "mednafen_pce_libretro.so",          "extensions": [".pce"]},
    "pcenginecd":      {"display_name": "PC Engine CD",                    "core": "mednafen_pce_libretro.so",          "extensions": [".chd", ".cue"]},
    "wswan":           {"display_name": "WonderSwan",                      "core": "mednafen_wswan_libretro.so",        "extensions": [".ws"]},
    "wswanc":          {"display_name": "WonderSwan Color",                "core": "mednafen_wswan_libretro.so",        "extensions": [".wsc"]},

    # ── Nintendo ──────────────────────────────────────────────────────────────
    "fds":             {"display_name": "Famicom Disk System",             "core": "mesen_libretro.so",                 "extensions": [".fds"]},
    "satellaview":     {"display_name": "Satellaview (BS-X)",              "core": "snes9x_libretro.so",                "extensions": [".bs"]},
    "sufami":          {"display_name": "Sufami Turbo",                    "core": "snes9x_libretro.so",                "extensions": [".st"]},
    "snes-msu1":       {"display_name": "Super Nintendo (MSU-1)",          "core": "snes9x_libretro.so",                "extensions": [".smc", ".sfc"]},
    "sgb":             {"display_name": "Super Game Boy",                  "core": "mesen_libretro.so",                 "extensions": [".gb", ".gbc"]},
    "gb2players":      {"display_name": "Game Boy (2-Player)",             "core": "gambatte_libretro.so",              "extensions": [".gb"]},
    "gbc2players":     {"display_name": "Game Boy Color (2-Player)",       "core": "gambatte_libretro.so",              "extensions": [".gbc"]},
    "n64dd":           {"display_name": "Nintendo 64DD",                   "core": "mupen64plus_next_libretro.so",      "extensions": [".ndd"]},
    "n3ds":            {"display_name": "Nintendo 3DS",                    "core": "citra_libretro.so",                 "extensions": [".3ds", ".cia"]},
    "gamecube":        {"display_name": "Nintendo GameCube",               "core": "dolphin_libretro.so",               "extensions": [".iso", ".gcm", ".rvz"]},
    "wii":             {"display_name": "Nintendo Wii",                    "core": "dolphin_libretro.so",               "extensions": [".iso", ".wbfs", ".rvz"]},
    "wiiu":            {"display_name": "Nintendo Wii U",                  "core": "",                                  "extensions": [".rpx", ".wud", ".wux"]},
    "switch":          {"display_name": "Nintendo Switch",                 "core": "",                                  "extensions": [".nsp", ".xci"]},
    "virtualboy":      {"display_name": "Nintendo Virtual Boy",            "core": "mednafen_vb_libretro.so",           "extensions": [".vb"]},
    "gameandwatch":    {"display_name": "Nintendo Game & Watch",           "core": "gw_libretro.so",                    "extensions": [".mgw"]},
    "pokemini":        {"display_name": "Pokémon Mini",                    "core": "pokemini_libretro.so",              "extensions": [".min"]},
    "supergrafx":      {"display_name": "PC Engine SuperGrafx",            "core": "mednafen_supergrafx_libretro.so",   "extensions": [".pce"]},

    # ── Sega ──────────────────────────────────────────────────────────────────
    "sg1000":          {"display_name": "Sega SG-1000",                    "core": "genesis_plus_gx_libretro.so",       "extensions": [".sg"]},
    "pico":            {"display_name": "Sega Pico",                       "core": "picodrive_libretro.so",             "extensions": [".md", ".bin"]},
    "msu-md":          {"display_name": "Mega Drive MSU-MD",               "core": "genesis_plus_gx_libretro.so",       "extensions": [".md", ".bin"]},
    "saturn":          {"display_name": "Sega Saturn",                     "core": "mednafen_saturn_libretro.so",       "extensions": [".chd", ".cue", ".iso"]},
    "dreamcast":       {"display_name": "Sega Dreamcast",                  "core": "flycast_libretro.so",               "extensions": [".chd", ".cdi", ".gdi"]},
    "naomi":           {"display_name": "Sega NAOMI",                      "core": "flycast_libretro.so",               "extensions": [".zip", ".chd"]},
    "naomi2":          {"display_name": "Sega NAOMI 2",                    "core": "flycast_libretro.so",               "extensions": [".zip", ".chd"]},
    "atomiswave":      {"display_name": "Sammy Atomiswave",                "core": "flycast_libretro.so",               "extensions": [".zip", ".chd"]},
    "megaduck":        {"display_name": "Cougar Boy / Mega Duck",          "core": "sameduck_libretro.so",              "extensions": [".bin"]},

    # ── Sony ──────────────────────────────────────────────────────────────────
    "ps2":             {"display_name": "PlayStation 2",                   "core": "pcsx2_libretro.so",                 "extensions": [".iso", ".chd"]},
    "psp":             {"display_name": "PlayStation Portable",            "core": "ppsspp_libretro.so",                "extensions": [".iso", ".cso", ".pbp"]},
    "ps3":             {"display_name": "PlayStation 3",                   "core": "",                                  "extensions": [".iso", ".pkg"]},
    "psvita":          {"display_name": "PlayStation Vita",                "core": "",                                  "extensions": [".vpk"]},

    # ── Microsoft ─────────────────────────────────────────────────────────────
    "xbox":            {"display_name": "Xbox",                            "core": "",                                  "extensions": [".iso", ".xbe"]},
    "xbox360":         {"display_name": "Xbox 360",                        "core": "",                                  "extensions": [".iso", ".xex"]},

    # ── Atari ─────────────────────────────────────────────────────────────────
    "atari5200":       {"display_name": "Atari 5200",                      "core": "atari800_libretro.so",              "extensions": [".a52"]},
    "atari800":        {"display_name": "Atari 800",                       "core": "atari800_libretro.so",              "extensions": [".atr", ".xex"]},
    "atarilynx":       {"display_name": "Atari Lynx",                      "core": "mednafen_lynx_libretro.so",         "extensions": [".lnx"]},
    "lynx":            {"display_name": "Atari Lynx",                      "core": "mednafen_lynx_libretro.so",         "extensions": [".lnx"]},
    "atarist":         {"display_name": "Atari ST",                        "core": "hatari_libretro.so",                "extensions": [".st", ".stx"]},
    "xegs":            {"display_name": "Atari XEGS",                      "core": "atari800_libretro.so",              "extensions": [".xex", ".atr"]},
    "jaguar":          {"display_name": "Atari Jaguar",                    "core": "virtualjaguar_libretro.so",         "extensions": [".j64", ".jag"]},
    "jaguarcd":        {"display_name": "Atari Jaguar CD",                 "core": "virtualjaguar_libretro.so",         "extensions": [".j64", ".cue"]},

    # ── SNK ───────────────────────────────────────────────────────────────────
    "neogeo":          {"display_name": "SNK Neo Geo",                     "core": "fbneo_libretro.so",                 "extensions": [".zip", ".neo"]},
    "neogeocd":        {"display_name": "SNK Neo Geo CD",                  "core": "neocd_libretro.so",                 "extensions": [".chd", ".cue"]},

    # ── Arcade ────────────────────────────────────────────────────────────────
    "mame":            {"display_name": "MAME",                            "core": "mame_libretro.so",                  "extensions": [".zip", ".chd"]},
    "fbneo":           {"display_name": "FinalBurn Neo",                   "core": "fbneo_libretro.so",                 "extensions": [".zip"]},
    "daphne":          {"display_name": "Daphne (LaserDisc)",              "core": "daphne_libretro.so",                "extensions": [".daphne"]},

    # ── Commodore ─────────────────────────────────────────────────────────────
    "c64":             {"display_name": "Commodore 64",                    "core": "vice_x64_libretro.so",              "extensions": [".d64", ".t64", ".prg"]},
    "c128":            {"display_name": "Commodore 128",                   "core": "vice_x128_libretro.so",             "extensions": [".d64", ".t64"]},
    "c20":             {"display_name": "Commodore VIC-20",                "core": "vice_xvic_libretro.so",             "extensions": [".d64", ".prg"]},
    "cplus4":          {"display_name": "Commodore Plus/4",                "core": "vice_xplus4_libretro.so",           "extensions": [".d64", ".prg"]},
    "pet":             {"display_name": "Commodore PET",                   "core": "vice_xpet_libretro.so",             "extensions": [".d64", ".prg"]},
    "amiga500":        {"display_name": "Commodore Amiga 500",             "core": "puae_libretro.so",                  "extensions": [".adf", ".hdf"]},
    "amiga1200":       {"display_name": "Commodore Amiga 1200",            "core": "puae_libretro.so",                  "extensions": [".adf", ".hdf"]},
    "amigacd32":       {"display_name": "Commodore Amiga CD32",            "core": "puae_libretro.so",                  "extensions": [".chd", ".cue"]},
    "amigacdtv":       {"display_name": "Commodore CDTV",                  "core": "puae_libretro.so",                  "extensions": [".chd", ".cue"]},

    # ── Sinclair / Amstrad ────────────────────────────────────────────────────
    "zxspectrum":      {"display_name": "Sinclair ZX Spectrum",            "core": "fuse_libretro.so",                  "extensions": [".tzx", ".tap", ".z80"]},
    "zx81":            {"display_name": "Sinclair ZX81",                   "core": "81_libretro.so",                    "extensions": [".p", ".tzx"]},
    "amstradcpc":      {"display_name": "Amstrad CPC",                     "core": "crocods_libretro.so",               "extensions": [".dsk", ".cdt"]},
    "gx4000":          {"display_name": "Amstrad GX4000",                  "core": "crocods_libretro.so",               "extensions": [".cpr"]},

    # ── Apple ─────────────────────────────────────────────────────────────────
    "apple2":          {"display_name": "Apple II",                        "core": "mednafen_apple2_libretro.so",       "extensions": [".dsk", ".po", ".nib"]},
    "apple2gs":        {"display_name": "Apple IIGS",                      "core": "gsplus_libretro.so",                "extensions": [".2mg", ".po"]},
    "macintosh":       {"display_name": "Apple Macintosh",                 "core": "minivmac_libretro.so",              "extensions": [".dsk", ".img"]},

    # ── NEC ───────────────────────────────────────────────────────────────────
    "pc88":            {"display_name": "NEC PC-8801",                     "core": "quasi88_libretro.so",               "extensions": [".d88", ".u88"]},
    "pc98":            {"display_name": "NEC PC-9801",                     "core": "np2kai_libretro.so",                "extensions": [".hdi", ".fdi", ".d98"]},

    # ── Sharp ─────────────────────────────────────────────────────────────────
    "x68000":          {"display_name": "Sharp X68000",                    "core": "px68k_libretro.so",                 "extensions": [".dim", ".img", ".xdf"]},
    "x1":              {"display_name": "Sharp X1",                        "core": "mame_libretro.so",                  "extensions": [".2d", ".dx1"]},

    # ── Fujitsu ───────────────────────────────────────────────────────────────
    "fm7":             {"display_name": "Fujitsu FM-7",                    "core": "mame_libretro.so",                  "extensions": [".d77", ".d88"]},
    "fmtowns":         {"display_name": "Fujitsu FM Towns",                "core": "mame_libretro.so",                  "extensions": [".bin", ".cue"]},

    # ── MSX ───────────────────────────────────────────────────────────────────
    "msx1":            {"display_name": "MSX1",                            "core": "bluemsx_libretro.so",               "extensions": [".rom", ".dsk", ".cas"]},
    "msx2":            {"display_name": "MSX2",                            "core": "bluemsx_libretro.so",               "extensions": [".rom", ".dsk", ".cas"]},
    "msx2+":           {"display_name": "MSX2+",                           "core": "bluemsx_libretro.so",               "extensions": [".rom", ".dsk"]},
    "msxturbor":       {"display_name": "MSX Turbo R",                     "core": "bluemsx_libretro.so",               "extensions": [".rom", ".dsk"]},
    "spectravideo":    {"display_name": "Spectravideo",                    "core": "bluemsx_libretro.so",               "extensions": [".rom", ".cas"]},

    # ── Mattel / Coleco / Magnavox ────────────────────────────────────────────
    "intellivision":   {"display_name": "Mattel Intellivision",            "core": "freeintv_libretro.so",              "extensions": [".int", ".bin"]},
    "colecovision":    {"display_name": "ColecoVision",                    "core": "bluemsx_libretro.so",               "extensions": [".col", ".rom"]},
    "o2em":            {"display_name": "Magnavox Odyssey 2",              "core": "o2em_libretro.so",                  "extensions": [".bin"]},
    "videopacplus":    {"display_name": "Philips Videopac+ G7400",         "core": "o2em_libretro.so",                  "extensions": [".bin"]},

    # ── Philips ───────────────────────────────────────────────────────────────
    "cdi":             {"display_name": "Philips CD-i",                    "core": "same_cdi_libretro.so",              "extensions": [".chd", ".iso"]},

    # ── Acorn ─────────────────────────────────────────────────────────────────
    "bbc":             {"display_name": "BBC Micro",                       "core": "mame_libretro.so",                  "extensions": [".ssd", ".dsd"]},
    "electron":        {"display_name": "Acorn Electron",                  "core": "mame_libretro.so",                  "extensions": [".uef", ".ssd"]},
    "archimedes":      {"display_name": "Acorn Archimedes",                "core": "mame_libretro.so",                  "extensions": [".adf"]},
    "atom":            {"display_name": "Acorn Atom",                      "core": "mame_libretro.so",                  "extensions": [".atm"]},

    # ── Texas Instruments / Tandy / Other home computers ─────────────────────
    "ti99":            {"display_name": "Texas Instruments TI-99/4A",      "core": "mess_libretro.so",                  "extensions": [".rpk", ".bin"]},
    "coco":            {"display_name": "TRS-80 Color Computer",           "core": "mess_libretro.so",                  "extensions": [".dsk", ".cas"]},
    "thomson":         {"display_name": "Thomson MO/TO",                   "core": "theodore_libretro.so",              "extensions": [".fd", ".sap"]},
    "dos":             {"display_name": "MS-DOS",                          "core": "dosbox_pure_libretro.so",           "extensions": [".exe", ".com", ".bat"]},
    "scummvm":         {"display_name": "ScummVM",                         "core": "scummvm_libretro.so",               "extensions": [".scummvm"]},

    # ── Handheld / portable ───────────────────────────────────────────────────
    "supervision":     {"display_name": "Watara Supervision",              "core": "potator_libretro.so",               "extensions": [".sv"]},
    "lcdgames":        {"display_name": "LCD Handheld Games",              "core": "gw_libretro.so",                    "extensions": [".mgw"]},
    "gamecom":         {"display_name": "Tiger Game.com",                  "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "gmaster":         {"display_name": "Hartung Game Master",             "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "gamate":          {"display_name": "Bit Corporation Gamate",          "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "gamepock":        {"display_name": "Epoch Game Pocket Computer",      "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "gp32":            {"display_name": "GamePark GP32",                   "core": "mame_libretro.so",                  "extensions": [".smc", ".bin"]},
    "arduboy":         {"display_name": "Arduboy",                         "core": "arduous_libretro.so",               "extensions": [".hex"]},
    "uzebox":          {"display_name": "Uzebox",                          "core": "uzem_libretro.so",                  "extensions": [".uze"]},
    "lowresnx":        {"display_name": "LowRes NX",                       "core": "lowresnx_libretro.so",              "extensions": [".nx"]},
    "tic80":           {"display_name": "TIC-80",                          "core": "tic80_libretro.so",                 "extensions": [".tic"]},
    "pico8":           {"display_name": "PICO-8",                          "core": "retro8_libretro.so",                "extensions": [".p8", ".png"]},
    "commanderx16":    {"display_name": "Commander X16",                   "core": "x16_libretro.so",                   "extensions": [".prg", ".bin"]},

    # ── Obscure / regional systems ────────────────────────────────────────────
    "adam":            {"display_name": "Coleco Adam",                     "core": "mess_libretro.so",                  "extensions": [".dsk", ".col"]},
    "advision":        {"display_name": "Entex Adventure Vision",          "core": "mess_libretro.so",                  "extensions": [".bin"]},
    "apfm1000":        {"display_name": "APF M-1000",                      "core": "mess_libretro.so",                  "extensions": [".bin"]},
    "arcadia":         {"display_name": "Emerson Arcadia 2001",            "core": "mess_libretro.so",                  "extensions": [".bin"]},
    "astrocde":        {"display_name": "Bally Astrocade",                 "core": "mess_libretro.so",                  "extensions": [".bin"]},
    "camplynx":        {"display_name": "Camputers Lynx",                  "core": "mame_libretro.so",                  "extensions": [".mly"]},
    "channelf":        {"display_name": "Fairchild Channel F",             "core": "freechaf_libretro.so",              "extensions": [".bin", ".chf"]},
    "crvision":        {"display_name": "VTech CreatiVision",              "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "laser310":        {"display_name": "VTech Laser 310",                 "core": "mame_libretro.so",                  "extensions": [".cas", ".vz"]},
    "multivision":     {"display_name": "Othello Multivision",             "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "pv1000":          {"display_name": "Casio PV-1000",                   "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "samcoupe":        {"display_name": "SAM Coupé",                       "core": "simcoupe_libretro.so",              "extensions": [".mgt", ".dsk"]},
    "scv":             {"display_name": "Epoch Super Cassette Vision",     "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "socrates":        {"display_name": "VTech Socrates",                  "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "supracan":        {"display_name": "Funtech Super A'Can",             "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "tutor":           {"display_name": "Tomy Tutor",                      "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "vc4000":          {"display_name": "Interton VC 4000",                "core": "mame_libretro.so",                  "extensions": [".bin"]},
    "vectrex":         {"display_name": "GCE Vectrex",                     "core": "vecx_libretro.so",                  "extensions": [".vec", ".bin"]},
    "vsmile":          {"display_name": "VTech V.Smile",                   "core": "mame_libretro.so",                  "extensions": [".bin"]},
}


SYSTEM_COMPATIBLE_CORES: dict[str, list[str]] = {
    # Game Boy / GBC
    "gb":              ["gambatte_libretro.so", "mgba_libretro.so", "sameboy_libretro.so", "tgbdual_libretro.so"],
    "gbc":             ["gambatte_libretro.so", "mgba_libretro.so", "sameboy_libretro.so", "tgbdual_libretro.so"],
    "gb2players":      ["gambatte_libretro.so", "mgba_libretro.so", "tgbdual_libretro.so"],
    "gbc2players":     ["gambatte_libretro.so", "mgba_libretro.so", "tgbdual_libretro.so"],
    "sgb":             ["mesen_libretro.so", "snes9x_libretro.so", "bsnes_libretro.so"],
    # GBA
    "gba":             ["mgba_libretro.so", "gpsp_libretro.so", "vba_next_libretro.so", "vbam_libretro.so"],
    # NES / FDS
    "nes":             ["mesen_libretro.so", "nestopia_libretro.so", "fceumm_libretro.so", "quicknes_libretro.so"],
    "fds":             ["mesen_libretro.so", "nestopia_libretro.so", "fceumm_libretro.so"],
    # SNES
    "snes":            ["snes9x_libretro.so", "bsnes_libretro.so", "mesen-s_libretro.so", "snes9x2010_libretro.so"],
    "snes-msu1":       ["snes9x_libretro.so", "bsnes_libretro.so"],
    "sufami":          ["snes9x_libretro.so", "bsnes_libretro.so"],
    "satellaview":     ["snes9x_libretro.so", "bsnes_libretro.so"],
    # N64
    "n64":             ["mupen64plus_next_libretro.so", "parallel_n64_libretro.so"],
    "n64dd":           ["mupen64plus_next_libretro.so", "parallel_n64_libretro.so"],
    # NDS
    "nds":             ["melonds_libretro.so", "desmume_libretro.so", "desmume2015_libretro.so"],
    # 3DS
    "n3ds":            ["citra_libretro.so"],
    # GameCube / Wii
    "gamecube":        ["dolphin_libretro.so"],
    "wii":             ["dolphin_libretro.so"],
    # Virtual Boy
    "virtualboy":      ["mednafen_vb_libretro.so"],
    # Game & Watch / Pokémon Mini
    "gameandwatch":    ["gw_libretro.so"],
    "pokemini":        ["pokemini_libretro.so"],
    # Sega Genesis / Mega Drive family
    "megadrive":       ["genesis_plus_gx_libretro.so", "picodrive_libretro.so", "blastem_libretro.so"],
    "sega32x":         ["picodrive_libretro.so"],
    "segacd":          ["genesis_plus_gx_libretro.so", "picodrive_libretro.so"],
    "mastersystem":    ["genesis_plus_gx_libretro.so", "picodrive_libretro.so", "smsplus_libretro.so"],
    "gamegear":        ["genesis_plus_gx_libretro.so", "picodrive_libretro.so"],
    "sg1000":          ["genesis_plus_gx_libretro.so"],
    "pico":            ["picodrive_libretro.so", "genesis_plus_gx_libretro.so"],
    "msu-md":          ["genesis_plus_gx_libretro.so"],
    "megaduck":        ["sameduck_libretro.so"],
    # Saturn
    "saturn":          ["mednafen_saturn_libretro.so", "yabause_libretro.so"],
    # Dreamcast / NAOMI
    "dreamcast":       ["flycast_libretro.so", "redream_libretro.so"],
    "naomi":           ["flycast_libretro.so"],
    "naomi2":          ["flycast_libretro.so"],
    "atomiswave":      ["flycast_libretro.so"],
    # PlayStation
    "psx":             ["mednafen_psx_hw_libretro.so", "mednafen_psx_libretro.so", "pcsx_rearmed_libretro.so", "swanstation_libretro.so"],
    "ps2":             ["pcsx2_libretro.so"],
    "psp":             ["ppsspp_libretro.so"],
    # PC Engine / TurboGrafx
    "pce":             ["mednafen_pce_libretro.so", "mednafen_pce_fast_libretro.so"],
    "pcengine":        ["mednafen_pce_libretro.so", "mednafen_pce_fast_libretro.so"],
    "pcenginecd":      ["mednafen_pce_libretro.so", "mednafen_pce_fast_libretro.so"],
    "supergrafx":      ["mednafen_supergrafx_libretro.so", "mednafen_pce_libretro.so"],
    # Neo Geo Pocket
    "ngp":             ["mednafen_ngp_libretro.so"],
    "ngpc":            ["mednafen_ngp_libretro.so"],
    # WonderSwan
    "wonderswan":      ["mednafen_wswan_libretro.so"],
    "wonderswancolor": ["mednafen_wswan_libretro.so"],
    "wswan":           ["mednafen_wswan_libretro.so"],
    "wswanc":          ["mednafen_wswan_libretro.so"],
    # Neo Geo / Arcade
    "neogeo":          ["fbneo_libretro.so", "mame_libretro.so"],
    "neogeocd":        ["neocd_libretro.so", "fbneo_libretro.so"],
    "fbneo":           ["fbneo_libretro.so", "mame_libretro.so"],
    "mame":            ["mame_libretro.so", "fbneo_libretro.so"],
    "daphne":          ["daphne_libretro.so"],
    # Atari
    "atari2600":       ["stella_libretro.so", "stella2014_libretro.so"],
    "atari7800":       ["prosystem_libretro.so"],
    "atari5200":       ["atari800_libretro.so"],
    "atari800":        ["atari800_libretro.so"],
    "atarilynx":       ["mednafen_lynx_libretro.so", "handy_libretro.so"],
    "lynx":            ["mednafen_lynx_libretro.so", "handy_libretro.so"],
    "atarist":         ["hatari_libretro.so"],
    "xegs":            ["atari800_libretro.so"],
    "jaguar":          ["virtualjaguar_libretro.so"],
    "jaguarcd":        ["virtualjaguar_libretro.so"],
    # Commodore
    "c64":             ["vice_x64_libretro.so", "vice_x64sc_libretro.so"],
    "c128":            ["vice_x128_libretro.so"],
    "c20":             ["vice_xvic_libretro.so"],
    "cplus4":          ["vice_xplus4_libretro.so"],
    "pet":             ["vice_xpet_libretro.so"],
    "amiga500":        ["puae_libretro.so", "uae4arm_libretro.so"],
    "amiga1200":       ["puae_libretro.so", "uae4arm_libretro.so"],
    "amigacd32":       ["puae_libretro.so"],
    "amigacdtv":       ["puae_libretro.so"],
    # MSX / Coleco
    "msx1":            ["bluemsx_libretro.so", "fmsx_libretro.so"],
    "msx2":            ["bluemsx_libretro.so", "fmsx_libretro.so"],
    "msx2+":           ["bluemsx_libretro.so", "fmsx_libretro.so"],
    "msxturbor":       ["bluemsx_libretro.so"],
    "spectravideo":    ["bluemsx_libretro.so"],
    "colecovision":    ["bluemsx_libretro.so", "gearcoleco_libretro.so"],
    # ZX Spectrum / Sinclair
    "zxspectrum":      ["fuse_libretro.so"],
    "zx81":            ["81_libretro.so"],
    # Amstrad
    "amstradcpc":      ["crocods_libretro.so", "cap32_libretro.so"],
    "gx4000":          ["crocods_libretro.so"],
    # Apple
    "apple2":          ["mednafen_apple2_libretro.so"],
    "apple2gs":        ["gsplus_libretro.so"],
    "macintosh":       ["minivmac_libretro.so"],
    # Japanese computers
    "pc88":            ["quasi88_libretro.so"],
    "pc98":            ["np2kai_libretro.so"],
    "x68000":          ["px68k_libretro.so"],
    "x1":              ["mame_libretro.so"],
    "fm7":             ["mame_libretro.so"],
    "fmtowns":         ["mame_libretro.so"],
    # DOS / ScummVM
    "dos":             ["dosbox_pure_libretro.so", "dosbox_core_libretro.so", "dosbox_svn_libretro.so"],
    "scummvm":         ["scummvm_libretro.so"],
    # Intellivision
    "intellivision":   ["freeintv_libretro.so"],
}


@dataclass
class SystemConfig:
    """Configuration for a single emulated system."""

    display_name: str
    core: str
    extensions: list[str] = field(default_factory=list)


class Config:
    """Application configuration.

    Loads ``~/.config/htpcstation/config.json`` on construction.
    If the file does not exist it is created with defaults.
    If the file is malformed a warning is logged and defaults are used.
    """

    def __init__(self) -> None:
        ensure_config_dir()

        self.retroarch_command: str = _DEFAULT_RETROARCH_COMMAND
        self.cores_directory: Path = Path(_DEFAULT_CORES_DIRECTORY).expanduser()
        self.rom_directory: Optional[Path] = None
        # Merged system configs: built-in defaults overridden by user config.
        self._systems: dict[str, SystemConfig] = {
            key: SystemConfig(**values) for key, values in SYSTEM_DEFAULTS.items()
        }
        # Plex Media Server configuration
        self._plex_token: Optional[str] = None
        self._plex_server_id: Optional[str] = None
        self._plex_user_id: Optional[int] = None
        self._plex_client_id: str = ""
        # Browser configuration
        self._browser_command: str = _DEFAULT_BROWSER_COMMAND
        # Moonlight configuration
        self._moonlight_command: str = _DEFAULT_MOONLIGHT_COMMAND
        self._moonlight_host_uuid: str = ""
        # UI settings
        self.video_snap_autoplay: bool = True
        self.video_snap_delay_ms: int = 1500
        self.show_network_indicator: bool = True
        self.button_layout: str = "standard"  # "standard" or "alternate"
        # Tab visibility settings
        self._show_retro_games_tab: bool = True
        self._show_pc_games_tab: bool = True
        self._show_moonlight_tab: bool = True
        self._show_watch_tab: bool = True
        self._show_listen_tab: bool = True
        # Music library selection
        self._music_library_key: str = ""
        # Plex player selection: "mpv" or "browser"
        self._plex_player: str = "mpv"
        # Auto-skip intro markers during Plex playback
        self._auto_skip_intro: bool = False
        # Sort preferences
        self._sort_retro_games: str = "az"
        self._sort_steam_games: str = "az"
        self._sort_moonlight_apps: str = "az"
        self._sort_plex_movies: str = ""
        self._sort_plex_shows: str = ""
        self._sort_plex_artists: str = ""
        self._filter_plex_movie_genre: str = ""
        self._filter_plex_show_genre: str = ""
        # View mode preferences
        self._retro_games_view_mode: str = "grid"
        self._pc_games_view_mode: str = "grid"
        self._moonlight_view_mode: str = "grid"
        self._watch_view_mode: str = "grid"
        self._listen_view_mode: str = "grid"

        if CONFIG_FILE.exists():
            self._load()
        else:
            self.save()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_system(self, folder_name: str) -> SystemConfig:
        """Return the SystemConfig for *folder_name*.

        Falls back to a minimal "unknown" config when the folder name is not
        recognised so callers never have to handle ``None``.
        """
        if folder_name in self._systems:
            return self._systems[folder_name]
        return SystemConfig(display_name=folder_name, core="", extensions=[])

    def get_launch_command(self, folder_name: str, rom_path: "str | Path") -> list[str]:
        """Build the RetroArch launch command for *rom_path* using the core
        configured for *folder_name*.

        Returns a list suitable for ``subprocess.run`` / ``QProcess``.
        """
        system = self.get_system(folder_name)
        core_path = self.cores_directory / system.core
        # Split the retroarch_command string into tokens so the caller gets a
        # proper argv list regardless of how the command is stored.
        command_tokens = self.retroarch_command.split()
        return [*command_tokens, "--fullscreen", "-L", str(core_path), str(rom_path)]

    @property
    def plex_token(self) -> Optional[str]:
        """Plex authentication token. None if not configured."""
        return self._plex_token

    @property
    def plex_server_id(self) -> Optional[str]:
        """Plex server machine identifier (clientIdentifier). None if not selected."""
        return self._plex_server_id

    @property
    def plex_user_id(self) -> Optional[int]:
        """Plex home user ID. None if not selected (uses admin account)."""
        return self._plex_user_id

    @property
    def plex_client_id(self) -> str:
        """Stable UUID identifying this HTPC Station installation."""
        if not self._plex_client_id:
            import uuid
            self._plex_client_id = str(uuid.uuid4())
            self.save()
        return self._plex_client_id

    @property
    def browser_command(self) -> str:
        """Browser launch command, e.g. 'flatpak run com.brave.Browser'."""
        return self._browser_command

    @property
    def moonlight_command(self) -> str:
        """Moonlight launch command, e.g. 'flatpak run com.moonlight_stream.Moonlight'."""
        return self._moonlight_command

    @property
    def moonlight_host_uuid(self) -> str:
        """UUID of the selected Moonlight host. Empty string if not configured."""
        return self._moonlight_host_uuid

    @property
    def music_library_key(self) -> str:
        """Plex section key of the selected music library. Empty string if not configured."""
        return self._music_library_key

    @property
    def plex_player(self) -> str:
        """Plex player selection: 'mpv' or 'browser'. Defaults to 'mpv'."""
        return self._plex_player

    def set_plex_player(self, player: str) -> None:
        """Set the Plex player and persist the config."""
        if player not in ("mpv", "browser"):
            logger.warning("set_plex_player: invalid value %r — ignored", player)
            return
        self._plex_player = player
        self.save()

    @property
    def auto_skip_intro(self) -> bool:
        """Whether to automatically skip intro markers during Plex playback."""
        return self._auto_skip_intro

    def set_auto_skip_intro(self, enabled: bool) -> None:
        """Set auto-skip intro and persist the config."""
        self._auto_skip_intro = bool(enabled)
        self.save()

    @property
    def sort_retro_games(self) -> str:
        """Persisted sort key for the retro games grid. Defaults to 'az'."""
        return self._sort_retro_games

    @property
    def sort_steam_games(self) -> str:
        """Persisted sort key for the Steam games grid. Defaults to 'az'."""
        return self._sort_steam_games

    @property
    def sort_moonlight_apps(self) -> str:
        """Persisted sort key for the Moonlight apps grid. Defaults to 'az'."""
        return self._sort_moonlight_apps

    @property
    def sort_plex_movies(self) -> str:
        """Persisted sort key for the Plex movies grid. Empty string means default order."""
        return self._sort_plex_movies

    @property
    def sort_plex_shows(self) -> str:
        """Persisted sort key for the Plex shows grid. Empty string means default order."""
        return self._sort_plex_shows

    @property
    def sort_plex_artists(self) -> str:
        """Persisted sort key for the Plex artists grid. Empty string means default order."""
        return self._sort_plex_artists

    @property
    def filter_plex_movie_genre(self) -> str:
        """Persisted genre filter key for Plex movies. Empty string means no filter."""
        return self._filter_plex_movie_genre

    @property
    def filter_plex_show_genre(self) -> str:
        """Persisted genre filter key for Plex shows. Empty string means no filter."""
        return self._filter_plex_show_genre

    @property
    def retro_games_view_mode(self) -> str:
        """Persisted view mode for the retro games screen. Either 'grid' or 'list'."""
        return self._retro_games_view_mode

    @property
    def pc_games_view_mode(self) -> str:
        """Persisted view mode for the PC games screen. Either 'grid' or 'list'."""
        return self._pc_games_view_mode

    @property
    def moonlight_view_mode(self) -> str:
        """Persisted view mode for the Moonlight screen. Either 'grid' or 'list'."""
        return self._moonlight_view_mode

    @property
    def watch_view_mode(self) -> str:
        """Persisted view mode for the Watch screen. Either 'grid' or 'list'."""
        return self._watch_view_mode

    @property
    def listen_view_mode(self) -> str:
        """Persisted view mode for the Listen screen. Either 'grid' or 'list'."""
        return self._listen_view_mode

    def set_rom_directory(self, path: "str | Path") -> None:
        """Set the ROM directory and persist the config."""
        self.rom_directory = Path(path).expanduser()
        self.save()

    def set_plex_token(self, token: str) -> None:
        """Set the Plex authentication token and persist the config."""
        self._plex_token = token if token else None
        self.save()

    def set_plex_server_id(self, server_id: str) -> None:
        """Set the Plex server machine identifier and persist the config."""
        self._plex_server_id = server_id if server_id else None
        self.save()

    def set_plex_user_id(self, user_id: int) -> None:
        """Set the Plex home user ID and persist the config."""
        self._plex_user_id = user_id if user_id else None
        self.save()

    def set_browser_command(self, command: str) -> None:
        """Set the browser launch command and persist the config."""
        self._browser_command = command
        self.save()

    def set_moonlight_command(self, command: str) -> None:
        """Set the Moonlight launch command and persist the config."""
        self._moonlight_command = command
        self.save()

    def set_moonlight_host_uuid(self, uuid: str) -> None:
        """Set the selected Moonlight host UUID and persist the config."""
        self._moonlight_host_uuid = uuid
        self.save()

    def set_music_library_key(self, key: str) -> None:
        """Set the selected Plex music library section key and persist the config."""
        self._music_library_key = key
        self.save()

    def set_sort_retro_games(self, key: str) -> None:
        """Set the sort preference for the retro games grid and persist the config."""
        self._sort_retro_games = key
        self.save()

    def set_sort_steam_games(self, key: str) -> None:
        """Set the sort preference for the Steam games grid and persist the config."""
        self._sort_steam_games = key
        self.save()

    def set_sort_moonlight_apps(self, key: str) -> None:
        """Set the sort preference for the Moonlight apps grid and persist the config."""
        self._sort_moonlight_apps = key
        self.save()

    def set_sort_plex_movies(self, key: str) -> None:
        """Set the sort preference for the Plex movies grid and persist the config."""
        self._sort_plex_movies = key
        self.save()

    def set_sort_plex_shows(self, key: str) -> None:
        """Set the sort preference for the Plex shows grid and persist the config."""
        self._sort_plex_shows = key
        self.save()

    def set_sort_plex_artists(self, key: str) -> None:
        """Set the sort preference for the Plex artists grid and persist the config."""
        self._sort_plex_artists = key
        self.save()

    def set_filter_plex_movie_genre(self, key: str) -> None:
        """Set the genre filter for Plex movies and persist the config."""
        self._filter_plex_movie_genre = key
        self.save()

    def set_filter_plex_show_genre(self, key: str) -> None:
        """Set the genre filter for Plex shows and persist the config."""
        self._filter_plex_show_genre = key
        self.save()

    def set_retro_games_view_mode(self, mode: str) -> None:
        """Set the view mode for the retro games screen and persist the config."""
        self._retro_games_view_mode = mode if mode in ("grid", "list") else "grid"
        self.save()

    def set_pc_games_view_mode(self, mode: str) -> None:
        """Set the view mode for the PC games screen and persist the config."""
        self._pc_games_view_mode = mode if mode in ("grid", "list") else "grid"
        self.save()

    def set_moonlight_view_mode(self, mode: str) -> None:
        """Set the view mode for the Moonlight screen and persist the config."""
        self._moonlight_view_mode = mode if mode in ("grid", "list") else "grid"
        self.save()

    def set_watch_view_mode(self, mode: str) -> None:
        """Set the view mode for the Watch screen and persist the config."""
        self._watch_view_mode = mode if mode in ("grid", "list") else "grid"
        self.save()

    def set_listen_view_mode(self, mode: str) -> None:
        """Set the view mode for the Listen screen and persist the config."""
        self._listen_view_mode = mode if mode in ("grid", "list") else "grid"
        self.save()

    def set_retroarch_command(self, command: str) -> None:
        """Set the RetroArch launch command and persist the config."""
        self.retroarch_command = command
        self.save()

    def set_cores_directory(self, path: str) -> None:
        """Set the RetroArch cores directory and persist the config."""
        self.cores_directory = Path(path).expanduser()
        self.save()

    def set_system_core(self, folder_name: str, core: str) -> None:
        """Set the core for a specific system and persist the config."""
        if folder_name in self._systems:
            self._systems[folder_name].core = core
        else:
            self._systems[folder_name] = SystemConfig(
                display_name=folder_name, core=core, extensions=[]
            )
        self.save()

    def set_video_snap_autoplay(self, enabled: bool) -> None:
        """Set the video snap autoplay toggle and persist the config."""
        self.video_snap_autoplay = enabled
        self.save()

    def set_video_snap_delay_ms(self, delay: int) -> None:
        """Set the video snap delay in milliseconds and persist the config."""
        self.video_snap_delay_ms = delay
        self.save()

    def set_show_network_indicator(self, enabled: bool) -> None:
        """Set the network indicator visibility toggle and persist the config."""
        self.show_network_indicator = enabled
        self.save()

    def set_button_layout(self, layout: str) -> None:
        """Set the button layout ('standard' or 'alternate') and persist the config."""
        if layout in ("standard", "alternate"):
            self.button_layout = layout
            self.save()

    @property
    def show_retro_games_tab(self) -> bool:
        """Whether the Retro Games tab is visible. Defaults to True."""
        return self._show_retro_games_tab

    @property
    def show_pc_games_tab(self) -> bool:
        """Whether the PC Games tab is visible. Defaults to True."""
        return self._show_pc_games_tab

    @property
    def show_moonlight_tab(self) -> bool:
        """Whether the Moonlight tab is visible. Defaults to True."""
        return self._show_moonlight_tab

    @property
    def show_watch_tab(self) -> bool:
        """Whether the Watch tab is visible. Defaults to True."""
        return self._show_watch_tab

    @property
    def show_listen_tab(self) -> bool:
        """Whether the Listen tab is visible. Defaults to True."""
        return self._show_listen_tab

    def set_show_retro_games_tab(self, enabled: bool) -> None:
        """Set the Retro Games tab visibility and persist the config."""
        self._show_retro_games_tab = enabled
        self.save()

    def set_show_pc_games_tab(self, enabled: bool) -> None:
        """Set the PC Games tab visibility and persist the config."""
        self._show_pc_games_tab = enabled
        self.save()

    def set_show_moonlight_tab(self, enabled: bool) -> None:
        """Set the Moonlight tab visibility and persist the config."""
        self._show_moonlight_tab = enabled
        self.save()

    def set_show_watch_tab(self, enabled: bool) -> None:
        """Set the Watch tab visibility and persist the config."""
        self._show_watch_tab = enabled
        self.save()

    def set_show_listen_tab(self, enabled: bool) -> None:
        """Set the Listen tab visibility and persist the config."""
        self._show_listen_tab = enabled
        self.save()

    def save(self) -> None:
        """Write the current configuration to ``config.json``."""
        try:
            ensure_config_dir()
        except OSError as exc:
            logger.warning("Config.save: could not create config dir %s: %s", CONFIG_DIR, exc)
            return
        data: dict = {
            "rom_directory": str(self.rom_directory) if self.rom_directory else "",
            "retroarch": {
                "command": self.retroarch_command,
                "cores_directory": str(self.cores_directory),
            },
            "systems": {
                key: {
                    "display_name": sc.display_name,
                    "core": sc.core,
                    "extensions": sc.extensions,
                }
                for key, sc in self._systems.items()
            },
            "plex": {
                "token": self._plex_token or "",
                "server_id": self._plex_server_id or "",
                "user_id": self._plex_user_id or 0,
                "client_id": self._plex_client_id,
                "music_library_key": self._music_library_key,
                "player": self._plex_player,
                "auto_skip_intro": self._auto_skip_intro,
            },
            "browser": {
                "command": self._browser_command,
            },
            "moonlight": {
                "command": self._moonlight_command,
                "host_uuid": self._moonlight_host_uuid,
            },
            "ui": {
                "video_snap_autoplay": self.video_snap_autoplay,
                "video_snap_delay_ms": self.video_snap_delay_ms,
                "show_network_indicator": self.show_network_indicator,
                "button_layout": self.button_layout,
                "retro_games_view_mode": self._retro_games_view_mode,
                "pc_games_view_mode": self._pc_games_view_mode,
                "moonlight_view_mode": self._moonlight_view_mode,
                "watch_view_mode": self._watch_view_mode,
                "listen_view_mode": self._listen_view_mode,
            },
            "sort_preferences": {
                "retro_games": self._sort_retro_games,
                "steam_games": self._sort_steam_games,
                "moonlight_apps": self._sort_moonlight_apps,
                "plex_movies": self._sort_plex_movies,
                "plex_shows": self._sort_plex_shows,
                "plex_artists": self._sort_plex_artists,
                "plex_movie_genre": self._filter_plex_movie_genre,
                "plex_show_genre": self._filter_plex_show_genre,
            },
            "tabs": {
                "show_retro_games": self._show_retro_games_tab,
                "show_pc_games": self._show_pc_games_tab,
                "show_moonlight": self._show_moonlight_tab,
                "show_watch": self._show_watch_tab,
                "show_listen": self._show_listen_tab,
            },
        }
        # Safety guard: never overwrite a config that has credentials with a blank one.
        if CONFIG_FILE.exists() and not self._plex_token and not self._plex_server_id:
            try:
                existing = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                if existing.get("plex", {}).get("token") or existing.get("plex", {}).get("server_id"):
                    logger.error(
                        "Config.save: refusing to overwrite config with credentials "
                        "— in-memory state has blank token/server_id. This is a bug."
                    )
                    return
            except (OSError, json.JSONDecodeError):
                pass  # can't read existing file — proceed with save
        try:
            CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Config.save: could not write %s: %s", CONFIG_FILE, exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load config from disk, merging with built-in defaults."""
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load config file %s: %s — using defaults", CONFIG_FILE, exc)
            return

        if not isinstance(raw, dict):
            logger.warning("Config file %s has unexpected format (not a JSON object) — using defaults", CONFIG_FILE)
            return

        # rom_directory
        rom_dir_raw: str = raw.get("rom_directory", "")
        if rom_dir_raw:
            self.rom_directory = Path(rom_dir_raw).expanduser()

        # retroarch section
        retroarch = raw.get("retroarch", {})
        if isinstance(retroarch, dict):
            if "command" in retroarch:
                self.retroarch_command = retroarch["command"]
            if "cores_directory" in retroarch:
                self.cores_directory = Path(retroarch["cores_directory"]).expanduser()

        # systems — merge: built-in defaults first, then user overrides
        user_systems: dict = raw.get("systems", {})
        if isinstance(user_systems, dict):
            for key, values in user_systems.items():
                if not isinstance(values, dict):
                    continue
                if key in self._systems:
                    # Update existing SystemConfig fields selectively
                    existing = self._systems[key]
                    existing.display_name = values.get("display_name", existing.display_name)
                    existing.core = values.get("core", existing.core)
                    existing.extensions = values.get("extensions", existing.extensions)
                else:
                    # Unknown system defined by user — add it
                    self._systems[key] = SystemConfig(
                        display_name=values.get("display_name", key),
                        core=values.get("core", ""),
                        extensions=values.get("extensions", []),
                    )

        # plex section
        plex = raw.get("plex", {})
        if isinstance(plex, dict):
            token = plex.get("token", "")
            if token:
                self._plex_token = token
            server_id = plex.get("server_id", "")
            if server_id:
                self._plex_server_id = server_id
            user_id = plex.get("user_id", 0)
            if user_id:
                self._plex_user_id = int(user_id)
            self._plex_client_id = plex.get("client_id", "")
            self._music_library_key = plex.get("music_library_key", "")
            player = plex.get("player", "mpv")
            if player in ("mpv", "browser"):
                self._plex_player = player
            self._auto_skip_intro = bool(plex.get("auto_skip_intro", False))
            # Backward compatibility: old configs may have server_url — ignore it gracefully

        # browser section
        browser = raw.get("browser", {})
        if isinstance(browser, dict):
            command = browser.get("command", "")
            if command:
                self._browser_command = command

        # moonlight section
        moonlight = raw.get("moonlight", {})
        if isinstance(moonlight, dict):
            command = moonlight.get("command", "")
            if command:
                self._moonlight_command = command
            self._moonlight_host_uuid = moonlight.get("host_uuid", "")

        # ui section
        ui = raw.get("ui", {})
        if isinstance(ui, dict):
            if "video_snap_autoplay" in ui:
                self.video_snap_autoplay = bool(ui["video_snap_autoplay"])
            if "video_snap_delay_ms" in ui:
                self.video_snap_delay_ms = int(ui["video_snap_delay_ms"])
            if "show_network_indicator" in ui:
                self.show_network_indicator = bool(ui["show_network_indicator"])
            if "button_layout" in ui and ui["button_layout"] in ("standard", "alternate"):
                self.button_layout = ui["button_layout"]
            raw_view_mode = ui.get("retro_games_view_mode", "grid")
            self._retro_games_view_mode = raw_view_mode if raw_view_mode in ("grid", "list") else "grid"
            raw_pc_view_mode = ui.get("pc_games_view_mode", "grid")
            self._pc_games_view_mode = raw_pc_view_mode if raw_pc_view_mode in ("grid", "list") else "grid"
            raw_moonlight_view_mode = ui.get("moonlight_view_mode", "grid")
            self._moonlight_view_mode = raw_moonlight_view_mode if raw_moonlight_view_mode in ("grid", "list") else "grid"
            raw_watch_view_mode = ui.get("watch_view_mode", "grid")
            self._watch_view_mode = raw_watch_view_mode if raw_watch_view_mode in ("grid", "list") else "grid"
            raw_listen_view_mode = ui.get("listen_view_mode", "grid")
            self._listen_view_mode = raw_listen_view_mode if raw_listen_view_mode in ("grid", "list") else "grid"

        # sort_preferences section
        sort_prefs = raw.get("sort_preferences", {})
        if isinstance(sort_prefs, dict):
            self._sort_retro_games = sort_prefs.get("retro_games", "az")
            self._sort_steam_games = sort_prefs.get("steam_games", "az")
            self._sort_moonlight_apps = sort_prefs.get("moonlight_apps", "az")
            self._sort_plex_movies = sort_prefs.get("plex_movies", "")
            self._sort_plex_shows = sort_prefs.get("plex_shows", "")
            self._sort_plex_artists = sort_prefs.get("plex_artists", "")
            self._filter_plex_movie_genre = sort_prefs.get("plex_movie_genre", "")
            self._filter_plex_show_genre = sort_prefs.get("plex_show_genre", "")

        # tabs section
        tabs = raw.get("tabs", {})
        if isinstance(tabs, dict):
            if "show_retro_games" in tabs:
                self._show_retro_games_tab = bool(tabs["show_retro_games"])
            if "show_pc_games" in tabs:
                self._show_pc_games_tab = bool(tabs["show_pc_games"])
            if "show_moonlight" in tabs:
                self._show_moonlight_tab = bool(tabs["show_moonlight"])
            if "show_watch" in tabs:
                self._show_watch_tab = bool(tabs["show_watch"])
            if "show_listen" in tabs:
                self._show_listen_tab = bool(tabs["show_listen"])


def ensure_config_dir() -> None:
    """Create the XDG config directory for htpcstation if it does not exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
