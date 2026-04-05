# Task Brief 001 — Interactive installer script

## Context

HTPC Station is a Qt6/QML + PySide6 media launcher. The repo lives at a user-chosen path;
`install.sh` sits at the repo root and is the entry point. Config is written to
`~/.config/htpcstation/config.json`. The config JSON structure is documented below.

`venv/` is already in `.gitignore` — no change needed there.

## Objective

Create `install.sh` at the repo root: an interactive CLI installer that detects the
environment, interviews the user, checks dependencies, sets up a Python venv, and writes
the initial config.

## Scope

**New files:**
- `install.sh` (repo root, `chmod +x`)

**No Python changes. No QML changes.**

---

## Script structure

Run top-to-bottom in these phases. Each phase is a clearly labelled shell function.

```
detect_environment
interview
check_dependencies
setup_venv
write_config
print_summary
```

---

## Phase 1 — detect_environment

### OS / distro family
Parse `/etc/os-release`. Map to one of: `debian` | `fedora` | `arch` | `unknown`.
- debian: ID_LIKE or ID contains `debian` or `ubuntu`
- fedora: ID_LIKE or ID contains `fedora` or `rhel`
- arch: ID_LIKE or ID contains `arch`

Store in `DISTRO_FAMILY`. If `unknown`, warn but continue — dependency check will still
run, just without install command suggestions.

### GPU
Run `lspci 2>/dev/null | grep -i "vga\|3d\|display"`. Parse output:
- Contains `Intel` → `GPU_VENDOR=intel`
- Contains `AMD` or `ATI` → `GPU_VENDOR=amd`
- Contains `NVIDIA` or `nvidia` → `GPU_VENDOR=nvidia`
- Multiple vendors found → `GPU_VENDOR=multiple`, set `GPU_CONFIDENCE=low`
- Nothing found → `GPU_VENDOR=unknown`, `GPU_CONFIDENCE=low`

If `GPU_CONFIDENCE=low`, prompt: "We couldn't confidently detect your GPU. Please select:
1) Intel  2) AMD  3) NVIDIA  4) Other"

### Session type
Read `$XDG_SESSION_TYPE`. Normalise to `wayland` or `x11`.
If unset or not one of those two values, prompt: "Display server not detected. Are you
running Wayland or Xorg/X11? [wayland/x11]"
Store in `SESSION_TYPE`.

### Python
Check `python3 --version`. Extract major.minor. Warn (but don't abort) if < 3.10.

### Existing config
If `~/.config/htpcstation/config.json` exists, set `EXISTING_CONFIG=1` and note the path.
Do not read or parse it at this stage.

---

## Phase 2 — interview

Print a short intro explaining what the script does. Then ask questions in order.
Use a `prompt_yn "Question" DEFAULT` helper that prints `[Y/n]` or `[y/N]` and reads input.
Use a `prompt_text "Question" DEFAULT` helper that shows the default in brackets.

All answers stored in shell variables for use in later phases.

### Q1 — Tabs
Ask which optional tabs to enable. Settings is always on.

```
Which tabs do you want to enable?
  [1] Retro Games  (requires RetroArch + ROMs)
  [2] PC Games     (requires Steam and/or Moonlight)
  [3] Watch        (requires Plex)
  [4] Listen       (requires Plex)
Enter numbers separated by spaces, or press Enter for all: _
```

Store as booleans: `TAB_RETRO`, `TAB_PC`, `TAB_WATCH`, `TAB_LISTEN`.

### Q2 — ROM directory (only if TAB_RETRO)
Auto-detect: check `~/ROMs`, `~/roms`, `~/Emulation`, `~/emulation` in order.
If found, show: "ROM directory detected: ~/ROMs — is this correct? [Y/n]"
If not found or user says no: `prompt_text "Enter ROM directory path" "~/ROMs"`
Expand `~` to `$HOME`. Store in `ROM_DIR`.

### Q3 — Plex server URL (only if TAB_WATCH or TAB_LISTEN)
Auto-detect: try `curl -s --connect-timeout 2 http://localhost:32400/identity` and common
LAN addresses (192.168.0.x, 192.168.1.x — scan .1 and .2 only, don't do a full subnet
scan). If a Plex server responds, show its URL and ask to confirm.
If not found: `prompt_text "Plex server URL" "http://localhost:32400"`
Store in `PLEX_SERVER_URL`. Strip trailing slash.

### Q4 — Plex hosting (only if TAB_WATCH or TAB_LISTEN)
`prompt_yn "Do you host your own Plex server on this network?" Y`
Store in `PLEX_LOCAL`. Informational only — no config key.

### Q5 — Plex Pass (only if TAB_WATCH or TAB_LISTEN)
`prompt_yn "Do you have a Plex Pass subscription?" N`
Store in `PLEX_PASS`. Informational only — no config key written.

### Q6 — HDHomeRun (only if TAB_WATCH)
`prompt_yn "Do you have an HDHomeRun tuner for Live TV?" N`
Store in `HAS_HDHOMERUN`. Informational only — Live TV is part of the Watch tab.

### Q7 — Steam / Moonlight (only if TAB_PC)
Check if `flatpak list 2>/dev/null | grep -q com.valvesoftware.Steam` and
`flatpak list 2>/dev/null | grep -q com.moonlight_stream.Moonlight`.
Report detected state, ask to confirm each.
Store in `HAS_STEAM`, `HAS_MOONLIGHT`.

### Q8 — Session type confirmation
Show detected `SESSION_TYPE` and ask to confirm if auto-detected with high confidence.
If low confidence, this was already asked in detect_environment.

---

## Phase 3 — check_dependencies

Print a section header. For each dependency, print one line:
```
  ✓ libmpv          (installed)
  ✗ python3-mpv     (missing) — install: sudo dnf install python3-mpv
```

Use colour: green ✓, red ✗. Use `tput` if available, plain text fallback.

### Dependency check helpers

`check_python_import NAME MODULE` — runs `python3 -c "import MODULE" 2>/dev/null`

`check_binary NAME` — runs `command -v NAME >/dev/null 2>&1`

`check_flatpak APP_ID` — runs `flatpak list 2>/dev/null | grep -q APP_ID`

`check_pkg_installed NAME` — distro-specific:
- debian: `dpkg -l NAME 2>/dev/null | grep -q "^ii"`
- fedora: `rpm -q NAME >/dev/null 2>&1`
- arch: `pacman -Q NAME >/dev/null 2>&1`
- unknown: skip check, mark as unknown

`install_cmd PACKAGES` — returns the install command string for the distro:
- debian: `sudo apt install PACKAGES`
- fedora: `sudo dnf install PACKAGES`
- arch: `sudo pacman -S PACKAGES`
- unknown: `# install: PACKAGES`

### Always-required dependencies

| What | Check method | Debian pkg | Fedora pkg | Arch pkg |
|---|---|---|---|---|
| python3 ≥ 3.10 | binary | `python3` | `python3` | `python3` |
| pip3 | binary | `python3-pip` | `python3-pip` | `python3-pip` |
| libmpv | `check_pkg_installed libmpv1` / `mpv-libs` / `libmpv` | `libmpv1` | `mpv-libs` | `mpv` |
| PySide6 | `check_python_import PySide6 PySide6` | `python3-pyside6` | `python3-pyside6` | `python3-pyside6` |
| python-mpv | `check_python_import mpv mpv` | `python3-mpv` | `python3-mpv` | `python3-mpv` |
| requests | `check_python_import requests requests` | `python3-requests` | `python3-requests` | `python3-requests` |
| evdev | `check_python_import evdev evdev` | `python3-evdev` | `python3-evdev` | `python3-evdev` |
| lspci | `check_binary lspci` | `pciutils` | `pciutils` | `pciutils` |

### GPU-specific VA-API drivers (always checked — needed for MPV hwdec)

| GPU | Debian | Fedora | Arch |
|---|---|---|---|
| intel | `intel-media-va-driver` or `i965-va-driver` | `libva-intel-driver` | `intel-media-driver` |
| amd | `mesa-va-drivers` | `mesa-va-drivers` | `mesa-vdpau-drivers` |
| nvidia | `nvidia-vaapi-driver` | `nvidia-vaapi-driver` | `libva-nvidia-driver` |

Note: on Fedora, warn if `ffmpeg-free` is installed instead of `ffmpeg` (RPM Fusion).
Check: `rpm -q ffmpeg-free >/dev/null 2>&1 && rpm -q ffmpeg >/dev/null 2>&1` — if
`ffmpeg-free` present and `ffmpeg` absent, print a warning about RPM Fusion.

### Tab-specific dependencies

**Retro Games:**
- RetroArch Flatpak: `check_flatpak org.libretro.RetroArch`

**PC Games:**
- Steam Flatpak: `check_flatpak com.valvesoftware.Steam` (if HAS_STEAM)
- Moonlight Flatpak: `check_flatpak com.moonlight_stream.Moonlight` (if HAS_MOONLIGHT)

**Watch / Listen:**
- curl: `check_binary curl` (used for Plex detection)

---

## Phase 4 — setup_venv

```
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$REPO_DIR/venv"
```

If `$VENV_DIR` already exists:
  - Print "Python venv already exists at $VENV_DIR — skipping creation."
  - Still run `$VENV_DIR/bin/pip install -q -r "$REPO_DIR/requirements.txt"` to ensure
    deps are up to date.

If not:
  - `python3 -m venv "$VENV_DIR"`
  - `$VENV_DIR/bin/pip install -q -r "$REPO_DIR/requirements.txt"`

Print result (success or error). On pip failure, warn but don't abort — system packages
may cover the deps.

---

## Phase 5 — write_config

Build the config JSON from interview answers. The config structure mirrors
`~/.config/htpcstation/config.json` as written by `backend/config.py`:

```json
{
  "plex": {
    "server_url": "<PLEX_SERVER_URL>",
    "token": "",
    "server_id": "",
    "player": "mpv"
  },
  "tabs": {
    "show_retro_games": <TAB_RETRO>,
    "show_pc_games": <TAB_PC>,
    "show_watch": <TAB_WATCH>,
    "show_listen": <TAB_LISTEN>
  },
  "rom_directory": "<ROM_DIR or empty string>",
  "retroarch": {
    "command": "flatpak run org.libretro.RetroArch",
    "cores_directory": "~/.var/app/org.libretro.RetroArch/config/retroarch/cores"
  },
  "gamepad": {},
  "theme": {}
}
```

Notes:
- `plex.server_url` only written if TAB_WATCH or TAB_LISTEN, else `""`
- `rom_directory` only written if TAB_RETRO, else `""`
- `plex.token` always `""` — set via in-app PIN login
- Do NOT write a `plex_pass` key — it's informational only

**Before writing:**
1. Print the full JSON that will be written.
2. If `EXISTING_CONFIG=1`:
   - Print "⚠ Existing config found at ~/.config/htpcstation/config.json"
   - `prompt_yn "Back up and overwrite?" N`
   - If yes: `cp config.json config.json.bak.$(date +%Y%m%d_%H%M%S)`, then write.
   - If no: skip write, print "Config not written. You can run install.sh again."
3. If no existing config: `prompt_yn "Write config?" Y`

Create `~/.config/htpcstation/` if it doesn't exist.

---

## Phase 6 — print_summary

Print a summary box:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  HTPC Station — Setup Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  OS:           Fedora (fedora)
  GPU:          Intel
  Session:      Wayland
  Python venv:  /home/user/opencode/htpcstation/venv

  Tabs enabled: Watch, Listen, Retro Games
  ROM dir:      /home/user/ROMs
  Plex server:  http://192.168.0.2:32400

  Missing deps: 2  (see above for install commands)

  Next steps:
  • Install missing dependencies listed above
  • Launch the app: venv/bin/python3 main.py
  • Sign in to Plex from the Settings tab
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If Plex Pass was answered yes, add:
  `• Some Plex features require Plex Pass (hardware transcoding)`

If HDHomeRun was answered yes, add:
  `• Live TV: HDHomeRun tuner will be auto-detected on the Watch tab`

---

## Style / UX rules

- Use `echo` not `printf` for portability unless formatting requires it
- Every prompt has a sensible default — user can press Enter to accept
- Never silently overwrite anything
- Colour via `tput setaf` / `tput sgr0` with `NO_COLOR` and non-tty fallback:
  ```bash
  if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && command -v tput >/dev/null 2>&1; then
      RED=$(tput setaf 1); GREEN=$(tput setaf 2); YELLOW=$(tput setaf 3)
      BOLD=$(tput bold); RESET=$(tput sgr0)
  else
      RED=''; GREEN=''; YELLOW=''; BOLD=''; RESET=''
  fi
  ```
- `set -euo pipefail` at the top — but wrap individual detection commands in
  `|| true` so failures don't abort the script
- Script must be POSIX-compatible bash (bash 4+, not sh)

## Constraints / Caveats

- The config JSON structure must exactly match what `backend/config.py` writes —
  read `backend/config.py` `_serialise()` method to confirm field names before writing
- `plex.server_url` is NOT a field in the current config — the app uses `plex.server_id`
  for server selection after PIN login. However, the installer should still ask for and
  store the server URL so the user has it noted. Store it under `plex.server_url` as a
  convenience field — the app will ignore unknown fields gracefully.
- Do not add a `plex_pass` key to the config — the app doesn't read it
- The `retroarch.cores_directory` default uses `~` literally (the app expands it) —
  write it as the literal string `~/.var/app/...`, not the expanded path
- lspci may not be available in all environments — wrap in `|| true`
