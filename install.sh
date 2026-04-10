#!/usr/bin/env bash
# HTPC Station — Interactive Installer
# Detects environment, interviews user, checks dependencies,
# sets up a Python venv, and writes the initial config.
set -euo pipefail

# ── Colour setup ─────────────────────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && command -v tput >/dev/null 2>&1; then
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BOLD=$(tput bold)
    RESET=$(tput sgr0)
else
    RED=''
    GREEN=''
    YELLOW=''
    BOLD=''
    RESET=''
fi

# ── Global state ──────────────────────────────────────────────────────────────
DISTRO_FAMILY="unknown"
GPU_VENDOR="unknown"
GPU_CONFIDENCE="high"
SESSION_TYPE=""
PYTHON_VERSION=""
EXISTING_CONFIG=0

TAB_RETRO=false
TAB_PC=false
TAB_WATCH=false
TAB_LISTEN=false

ROM_DIR=""
PLEX_SERVER_URL=""
PLEX_LOCAL=false
PLEX_PASS=false
HAS_HDHOMERUN=false
HAS_STEAM=false
HAS_MOONLIGHT=false

MISSING_DEPS=0
MISSING_DEP_CMDS=()

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$REPO_DIR/venv"
CONFIG_FILE="$HOME/.config/htpcstation/config.json"

# ── Helper: prompt yes/no ─────────────────────────────────────────────────────
# Usage: prompt_yn "Question" DEFAULT
# DEFAULT is Y or N (case-insensitive). Returns 0 for yes, 1 for no.
prompt_yn() {
    local question="$1"
    local default="${2:-Y}"
    local prompt_str
    if [ "$(echo "$default" | tr '[:lower:]' '[:upper:]')" = "Y" ]; then
        prompt_str="[Y/n]"
    else
        prompt_str="[y/N]"
    fi
    while true; do
        printf "%s %s " "$question" "$prompt_str" > /dev/tty
        read -r answer < /dev/tty
        answer="${answer:-$default}"
        case "$(echo "$answer" | tr '[:lower:]' '[:upper:]')" in
            Y|YES) return 0 ;;
            N|NO)  return 1 ;;
            *) echo "  Please enter y or n." ;;
        esac
    done
}

# ── Helper: prompt text ───────────────────────────────────────────────────────
# Usage: prompt_text "Question" DEFAULT
# Prints the default in brackets. Returns the entered value (or default).
prompt_text() {
    local question="$1"
    local default="${2:-}"
    printf "%s [%s]: " "$question" "$default" > /dev/tty
    read -r answer < /dev/tty
    if [ -z "$answer" ]; then
        echo "$default"
    else
        echo "$answer"
    fi
}

# Like prompt_text but with readline tab completion — bash only, for path inputs.
prompt_path() {
    local question="$1"
    local default="${2:-}"
    local answer
    # -e enables readline (tab completion, arrow keys)
    # -i pre-fills the input with the default
    # -p prints the prompt via readline so it handles the terminal correctly
    read -e -i "$default" -p "  ${question} [${default}]: " answer < /dev/tty
    # Expand leading ~ to $HOME
    answer="${answer/#\~/$HOME}"
    if [ -z "$answer" ]; then
        echo "$default"
    else
        echo "$answer"
    fi
}

# ── Phase 1: detect_environment ───────────────────────────────────────────────
detect_environment() {
    echo ""
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo "${BOLD}  Phase 1: Detecting Environment${RESET}"
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

    # OS / distro family
    if [ -f /etc/os-release ]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        local id_val="${ID:-}"
        local id_like_val="${ID_LIKE:-}"
        local combined="${id_val} ${id_like_val}"
        combined=$(echo "$combined" | tr '[:upper:]' '[:lower:]')
        if echo "$combined" | grep -qE "debian|ubuntu"; then
            DISTRO_FAMILY="debian"
        elif echo "$combined" | grep -qE "fedora|rhel"; then
            DISTRO_FAMILY="fedora"
        elif echo "$combined" | grep -qE "arch"; then
            DISTRO_FAMILY="arch"
        else
            DISTRO_FAMILY="unknown"
        fi
    else
        DISTRO_FAMILY="unknown"
    fi

    if [ "$DISTRO_FAMILY" = "unknown" ]; then
        echo "  ${YELLOW}⚠ Could not detect distro family — dependency install suggestions will be unavailable.${RESET}"
    else
        echo "  Distro family: ${BOLD}${DISTRO_FAMILY}${RESET}"
    fi

    # Graphics detection
    local lspci_out=""
    lspci_out=$(lspci 2>/dev/null | grep -iE "vga|3d|display" || true)

    local has_intel=false
    local has_amd=false
    local has_nvidia=false

    if echo "$lspci_out" | grep -qi "Intel"; then
        has_intel=true
    fi
    if echo "$lspci_out" | grep -qiwE "AMD|ATI"; then
        has_amd=true
    fi
    if echo "$lspci_out" | grep -qiE "NVIDIA|nvidia"; then
        has_nvidia=true
    fi

    local vendor_count=0
    $has_intel  && vendor_count=$((vendor_count + 1)) || true
    $has_amd    && vendor_count=$((vendor_count + 1)) || true
    $has_nvidia && vendor_count=$((vendor_count + 1)) || true

    if [ "$vendor_count" -gt 1 ]; then
        GPU_VENDOR="multiple"
        GPU_CONFIDENCE="low"
    elif $has_intel; then
        GPU_VENDOR="intel"
    elif $has_amd; then
        GPU_VENDOR="amd"
    elif $has_nvidia; then
        GPU_VENDOR="nvidia"
    else
        GPU_VENDOR="unknown"
        GPU_CONFIDENCE="low"
    fi

    if [ "$GPU_CONFIDENCE" = "low" ]; then
        echo "  ${YELLOW}⚠ Could not confidently detect your graphics (detected: ${GPU_VENDOR}).${RESET}"
        echo "  Please select your primary graphics:"
        echo "    1) Intel   (onboard / integrated)"
        echo "    2) AMD     (onboard Ryzen or discrete Radeon)"
        echo "    3) NVIDIA  (discrete)"
        echo "    4) Other"
        echo ""
        echo "  ${YELLOW}Note: for media playback, onboard graphics (Intel or AMD) usually give${RESET}"
        echo "  ${YELLOW}better hardware decode support than a discrete NVIDIA card on Linux.${RESET}"
        echo "  ${YELLOW}If you have both, choose your onboard option.${RESET}"
        echo ""
        while true; do
            printf "  Enter choice [1-4]: " > /dev/tty
            read -r gpu_choice < /dev/tty
            case "$gpu_choice" in
                1) GPU_VENDOR="intel";   GPU_CONFIDENCE="high"; break ;;
                2) GPU_VENDOR="amd";     GPU_CONFIDENCE="high"; break ;;
                3) GPU_VENDOR="nvidia";  GPU_CONFIDENCE="high"; break ;;
                4) GPU_VENDOR="other";   GPU_CONFIDENCE="high"; break ;;
                *) echo "  Please enter 1, 2, 3, or 4." ;;
            esac
        done
    fi
    echo "  Graphics: ${BOLD}${GPU_VENDOR}${RESET}"

    # Session type
    local xdg_session="${XDG_SESSION_TYPE:-}"
    case "$(echo "$xdg_session" | tr '[:upper:]' '[:lower:]')" in
        wayland) SESSION_TYPE="wayland" ;;
        x11)     SESSION_TYPE="x11" ;;
        *)
            echo "  ${YELLOW}⚠ Display server not detected (XDG_SESSION_TYPE='${xdg_session}').${RESET}"
            while true; do
                printf "  Are you running Wayland or Xorg/X11? [wayland/x11]: " > /dev/tty
                read -r session_answer < /dev/tty
                case "$(echo "$session_answer" | tr '[:upper:]' '[:lower:]')" in
                    wayland) SESSION_TYPE="wayland"; break ;;
                    x11)     SESSION_TYPE="x11";     break ;;
                    *) echo "  Please enter 'wayland' or 'x11'." ;;
                esac
            done
            ;;
    esac
    echo "  Session type: ${BOLD}${SESSION_TYPE}${RESET}"

    # Python version
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        local py_major py_minor
        py_major=$(echo "$PYTHON_VERSION" | cut -d. -f1)
        py_minor=$(echo "$PYTHON_VERSION" | cut -d. -f2)
        echo "  Python: ${BOLD}${PYTHON_VERSION}${RESET}"
        if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt 10 ]; }; then
            echo "  ${YELLOW}⚠ Python ${PYTHON_VERSION} is below the recommended minimum of 3.10.${RESET}"
        fi
    else
        echo "  ${YELLOW}⚠ python3 not found in PATH.${RESET}"
        PYTHON_VERSION="not found"
    fi

    # Existing config
    if [ -f "$CONFIG_FILE" ]; then
        EXISTING_CONFIG=1
        echo "  ${YELLOW}⚠ Existing config found at ${CONFIG_FILE}${RESET}"
    fi
}

# ── Phase 2: interview ────────────────────────────────────────────────────────
interview() {
    echo ""
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo "${BOLD}  Phase 2: Setup Interview${RESET}"
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
    echo "  This script will configure HTPC Station for your system."
    echo "  It will set up a Python virtual environment and write an"
    echo "  initial config to ${CONFIG_FILE}."
    echo "  The Settings tab is always enabled."
    echo ""

    # Q1 — Tabs
    echo "  Which tabs do you want to enable?"
    echo "    [1] Retro Games  (requires RetroArch + ROMs)"
    echo "    [2] PC Games     (requires Steam and/or Moonlight)"
    echo "    [3] Plex Media   (requires Plex)"
    echo "    [4] Plex Music   (requires Plex)"
    printf "  Enter numbers separated by spaces, or press Enter for all: " > /dev/tty
    read -r tab_input < /dev/tty

    if [ -z "$tab_input" ]; then
        TAB_RETRO=true
        TAB_PC=true
        TAB_WATCH=true
        TAB_LISTEN=true
    else
        for num in $tab_input; do
            case "$num" in
                1) TAB_RETRO=true ;;
                2) TAB_PC=true ;;
                3) TAB_WATCH=true ;;
                4) TAB_LISTEN=true ;;
                *) echo "  ${YELLOW}⚠ Unknown tab number: ${num} — ignored.${RESET}" ;;
            esac
        done
    fi

    # Q2 — ROM directory (only if TAB_RETRO)
    if $TAB_RETRO; then
        echo ""
        local detected_rom_dir=""
        for candidate in "$HOME/ROMs" "$HOME/roms" "$HOME/Emulation" "$HOME/emulation"; do
            if [ -d "$candidate" ]; then
                detected_rom_dir="$candidate"
                break
            fi
        done

        if [ -n "$detected_rom_dir" ]; then
            local display_candidate
            display_candidate=$(echo "$detected_rom_dir" | sed "s|^$HOME|~|")
            if prompt_yn "  ROM directory detected: ${display_candidate} — is this correct?" Y; then
                ROM_DIR="$detected_rom_dir"
            else
                ROM_DIR=$(prompt_path "Enter ROM directory path" "~/ROMs")
            fi
        else
            ROM_DIR=$(prompt_path "Enter ROM directory path" "~/ROMs")
        fi
        echo "  ROM directory: ${BOLD}${ROM_DIR}${RESET}"
    fi

    # Q3 — Plex server URL (only if TAB_WATCH or TAB_LISTEN)
    if $TAB_WATCH || $TAB_LISTEN; then
        echo ""
        echo "  Scanning for Plex server..."
        local detected_plex_url=""

        # Try localhost first
        if command -v curl >/dev/null 2>&1; then
            if curl -s --connect-timeout 2 "http://localhost:32400/identity" >/dev/null 2>&1; then
                detected_plex_url="http://localhost:32400"
            fi

            # Try common LAN addresses if localhost not found
            if [ -z "$detected_plex_url" ]; then
                for subnet in "192.168.0" "192.168.1"; do
                    for host in 1 2; do
                        local candidate_url="http://${subnet}.${host}:32400"
                        if curl -s --connect-timeout 2 "${candidate_url}/identity" >/dev/null 2>&1; then
                            detected_plex_url="$candidate_url"
                            break 2
                        fi
                    done
                done
            fi
        fi

        if [ -n "$detected_plex_url" ]; then
            if prompt_yn "  Plex server detected at ${detected_plex_url} — use this?" Y; then
                PLEX_SERVER_URL="$detected_plex_url"
            else
                PLEX_SERVER_URL=$(prompt_text "  Plex server URL" "http://localhost:32400")
            fi
        else
            PLEX_SERVER_URL=$(prompt_text "  Plex server URL" "http://localhost:32400")
        fi

        # Strip trailing slash
        PLEX_SERVER_URL="${PLEX_SERVER_URL%/}"
        echo "  Plex server URL: ${BOLD}${PLEX_SERVER_URL}${RESET}"

        # Q4 — Plex hosting
        echo ""
        if prompt_yn "  Do you host your own Plex server on this network?" Y; then
            PLEX_LOCAL=true
        else
            PLEX_LOCAL=false
        fi

        # Q5 — Plex Pass
        if prompt_yn "  Do you have a Plex Pass subscription?" N; then
            PLEX_PASS=true
        else
            PLEX_PASS=false
        fi

        # Q6 — HDHomeRun (only if TAB_WATCH)
        if $TAB_WATCH; then
            if prompt_yn "  Do you have an HDHomeRun tuner for Live TV?" N; then
                HAS_HDHOMERUN=true
            else
                HAS_HDHOMERUN=false
            fi
        fi
    fi

    # Q7 — Steam / Moonlight (only if TAB_PC)
    if $TAB_PC; then
        echo ""
        local steam_detected=false
        local moonlight_detected=false

        if flatpak list 2>/dev/null | grep -q "com.valvesoftware.Steam"; then
            steam_detected=true
        fi
        if flatpak list 2>/dev/null | grep -q "com.moonlight_stream.Moonlight"; then
            moonlight_detected=true
        fi

        if $steam_detected; then
            echo "  Steam (Flatpak) detected."
            if prompt_yn "  Use Steam for PC Games?" Y; then
                HAS_STEAM=true
            else
                HAS_STEAM=false
            fi
        else
            echo "  Steam (Flatpak) not detected."
            if prompt_yn "  Do you plan to use Steam for PC Games?" N; then
                HAS_STEAM=true
            else
                HAS_STEAM=false
            fi
        fi

        if $moonlight_detected; then
            echo "  Moonlight (Flatpak) detected."
            if prompt_yn "  Use Moonlight for PC Games?" Y; then
                HAS_MOONLIGHT=true
            else
                HAS_MOONLIGHT=false
            fi
        else
            echo "  Moonlight (Flatpak) not detected."
            if prompt_yn "  Do you plan to use Moonlight for PC Games?" N; then
                HAS_MOONLIGHT=true
            else
                HAS_MOONLIGHT=false
            fi
        fi
    fi

    # Q8 — Session type confirmation (if auto-detected with high confidence)
    echo ""
    if prompt_yn "  Confirm session type '${SESSION_TYPE}'?" Y; then
        : # keep SESSION_TYPE as-is
    else
        while true; do
            printf "  Enter session type [wayland/x11]: " > /dev/tty
            read -r session_answer < /dev/tty
            case "$(echo "$session_answer" | tr '[:upper:]' '[:lower:]')" in
                wayland) SESSION_TYPE="wayland"; break ;;
                x11)     SESSION_TYPE="x11";     break ;;
                *) echo "  Please enter 'wayland' or 'x11'." ;;
            esac
        done
    fi
}

# ── Dependency check helpers ──────────────────────────────────────────────────
check_python_import() {
    local name="$1"
    local module="$2"
    python3 -c "import ${module}" 2>/dev/null
}

check_binary() {
    local name="$1"
    command -v "$name" >/dev/null 2>&1
}

check_flatpak() {
    local app_id="$1"
    flatpak list 2>/dev/null | grep -q "$app_id"
}

check_pkg_installed() {
    local name="$1"
    case "$DISTRO_FAMILY" in
        debian) dpkg -l "$name" 2>/dev/null | grep -q "^ii" ;;
        fedora) rpm -q "$name" >/dev/null 2>&1 ;;
        arch)   pacman -Q "$name" >/dev/null 2>&1 ;;
        *)      return 2 ;;  # unknown — skip
    esac
}

install_cmd() {
    local packages="$1"
    case "$DISTRO_FAMILY" in
        debian)  echo "sudo apt install ${packages}" ;;
        fedora)  echo "sudo dnf install ${packages}" ;;
        arch)    echo "sudo pacman -S ${packages}" ;;
        *)       echo "# install: ${packages}" ;;
    esac
}

# Print one dependency check line
# Usage: report_dep NAME STATUS INSTALL_HINT
report_dep() {
    local name="$1"
    local status="$2"   # "ok", "missing", "unknown"
    local hint="${3:-}"

    case "$status" in
        ok)
            echo "  ${GREEN}✓${RESET} ${name}  (installed)"
            ;;
        missing)
            echo "  ${RED}✗${RESET} ${name}  (missing)${hint:+ — install: ${hint}}"
            MISSING_DEPS=$((MISSING_DEPS + 1))
            [ -n "$hint" ] && MISSING_DEP_CMDS+=("$hint")
            ;;
        unknown)
            echo "  ${YELLOW}?${RESET} ${name}  (status unknown — distro not recognised)"
            ;;
    esac
}

# ── Phase 3: check_dependencies ───────────────────────────────────────────────
check_dependencies() {
    echo ""
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo "${BOLD}  Phase 3: Checking Dependencies${RESET}"
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""

    # python3
    if check_binary python3; then
        report_dep "python3" "ok"
    else
        report_dep "python3" "missing" "$(install_cmd "python3")"
    fi

    # pip3
    if check_binary pip3; then
        report_dep "pip3" "ok"
    else
        report_dep "pip3" "missing" "$(install_cmd "python3-pip")"
    fi

    # libmpv — package name differs by distro
    local libmpv_pkg
    case "$DISTRO_FAMILY" in
        debian)  libmpv_pkg="libmpv1" ;;
        fedora)  libmpv_pkg="mpv-libs" ;;
        arch)    libmpv_pkg="mpv" ;;
        *)       libmpv_pkg="" ;;
    esac

    if [ -z "$libmpv_pkg" ]; then
        report_dep "libmpv" "unknown"
    else
        local libmpv_status
        if check_pkg_installed "$libmpv_pkg" 2>/dev/null; then
            libmpv_status="ok"
        else
            libmpv_status="missing"
        fi
        report_dep "libmpv" "$libmpv_status" "$(install_cmd "$libmpv_pkg")"
    fi

    # PySide6
    if check_python_import "PySide6" "PySide6" 2>/dev/null; then
        report_dep "PySide6" "ok"
    else
        report_dep "PySide6" "missing" "$(install_cmd "python3-pyside6")"
    fi

    # python-mpv
    if check_python_import "mpv" "mpv" 2>/dev/null; then
        report_dep "python-mpv" "ok"
    else
        report_dep "python-mpv" "missing" "$(install_cmd "python3-mpv")"
    fi

    # requests
    if check_python_import "requests" "requests" 2>/dev/null; then
        report_dep "requests" "ok"
    else
        report_dep "requests" "missing" "$(install_cmd "python3-requests")"
    fi

    # evdev
    if check_python_import "evdev" "evdev" 2>/dev/null; then
        report_dep "evdev" "ok"
    else
        report_dep "evdev" "missing" "$(install_cmd "python3-evdev")"
    fi

    # mutagen
    if check_python_import "mutagen" "mutagen" 2>/dev/null; then
        report_dep "mutagen" "ok"
    else
        report_dep "mutagen" "missing" "$(install_cmd "python3-mutagen")"
    fi

    # lspci
    if check_binary lspci; then
        report_dep "lspci" "ok"
    else
        report_dep "lspci" "missing" "$(install_cmd "pciutils")"
    fi

    # GPU-specific VA-API drivers
    echo ""
    echo "  ${BOLD}VA-API / hardware decode drivers:${RESET}"
    local vaapi_pkg=""
    case "$GPU_VENDOR" in
        intel)
            case "$DISTRO_FAMILY" in
                debian) vaapi_pkg="intel-media-va-driver" ;;
                fedora) vaapi_pkg="libva-intel-driver" ;;
                arch)   vaapi_pkg="intel-media-driver" ;;
            esac
            ;;
        amd)
            case "$DISTRO_FAMILY" in
                debian) vaapi_pkg="mesa-va-drivers" ;;
                fedora) vaapi_pkg="mesa-va-drivers" ;;
                arch)   vaapi_pkg="mesa-vdpau-drivers" ;;
            esac
            ;;
        nvidia)
            case "$DISTRO_FAMILY" in
                debian) vaapi_pkg="nvidia-vaapi-driver" ;;
                fedora) vaapi_pkg="nvidia-vaapi-driver" ;;
                arch)   vaapi_pkg="libva-nvidia-driver" ;;
            esac
            ;;
    esac

    if [ -n "$vaapi_pkg" ] && [ "$DISTRO_FAMILY" != "unknown" ]; then
        local vaapi_status
        if check_pkg_installed "$vaapi_pkg" 2>/dev/null; then
            vaapi_status="ok"
        else
            vaapi_status="missing"
        fi
        report_dep "${vaapi_pkg} (VA-API for ${GPU_VENDOR})" "$vaapi_status" "$(install_cmd "$vaapi_pkg")"
    else
        echo "  ${YELLOW}?${RESET} VA-API driver  (GPU vendor '${GPU_VENDOR}' — check manually)"
    fi

    # Fedora: warn about ffmpeg-free vs ffmpeg
    if [ "$DISTRO_FAMILY" = "fedora" ]; then
        if rpm -q ffmpeg-free >/dev/null 2>&1 && ! rpm -q ffmpeg >/dev/null 2>&1; then
            echo ""
            echo "  ${YELLOW}⚠ Fedora: 'ffmpeg-free' is installed but 'ffmpeg' (RPM Fusion) is not.${RESET}"
            echo "    MPV hardware decoding may be limited. Consider enabling RPM Fusion and"
            echo "    installing 'ffmpeg' for full codec support."
        fi
    fi

    # Tab-specific dependencies
    if $TAB_RETRO; then
        echo ""
        echo "  ${BOLD}Retro Games:${RESET}"
        if check_flatpak "org.libretro.RetroArch" 2>/dev/null; then
            report_dep "RetroArch (Flatpak)" "ok"
        else
            report_dep "RetroArch (Flatpak)" "missing" "flatpak install flathub org.libretro.RetroArch"
        fi
    fi

    if $TAB_PC; then
        echo ""
        echo "  ${BOLD}PC Games:${RESET}"
        if $HAS_STEAM; then
            if check_flatpak "com.valvesoftware.Steam" 2>/dev/null; then
                report_dep "Steam (Flatpak)" "ok"
            else
                report_dep "Steam (Flatpak)" "missing" "flatpak install flathub com.valvesoftware.Steam"
            fi
        fi
        if $HAS_MOONLIGHT; then
            if check_flatpak "com.moonlight_stream.Moonlight" 2>/dev/null; then
                report_dep "Moonlight (Flatpak)" "ok"
            else
                report_dep "Moonlight (Flatpak)" "missing" "flatpak install flathub com.moonlight_stream.Moonlight"
            fi
        fi
    fi

    if $TAB_WATCH || $TAB_LISTEN; then
        echo ""
        echo "  ${BOLD}Watch / Listen:${RESET}"
        if check_binary curl; then
            report_dep "curl" "ok"
        else
            report_dep "curl" "missing" "$(install_cmd "curl")"
        fi
    fi
}

# ── Offer to install missing dependencies ────────────────────────────────────
offer_install_missing() {
    if [ "${#MISSING_DEP_CMDS[@]}" -eq 0 ]; then
        return
    fi

    echo ""
    echo "${BOLD}  Would you like to install missing dependencies?${RESET}"
    echo ""

    local failed_cmds=()

    for cmd in "${MISSING_DEP_CMDS[@]}"; do
        if prompt_yn "  Install: ${cmd}?" "y"; then
            echo "  Running: ${cmd}"
            if eval "$cmd"; then
                echo "  ${GREEN}✓${RESET} Success"
            else
                echo "  ${RED}✗${RESET} Command failed: ${cmd}"
                failed_cmds+=("$cmd")
            fi
        else
            failed_cmds+=("$cmd")
        fi
    done

    # Rebuild MISSING_DEPS and MISSING_DEP_CMDS to reflect current state
    MISSING_DEPS="${#failed_cmds[@]}"
    MISSING_DEP_CMDS=()
    if [ "${#failed_cmds[@]}" -gt 0 ]; then
        MISSING_DEP_CMDS=("${failed_cmds[@]}")
    fi
}

# ── Phase 4: setup_venv ───────────────────────────────────────────────────────
setup_venv() {
    echo ""
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo "${BOLD}  Phase 4: Python Virtual Environment${RESET}"
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""

    if [ -d "$VENV_DIR" ]; then
        if [ -x "$VENV_DIR/bin/python3" ] && [ -x "$VENV_DIR/bin/pip" ]; then
            echo "  Python venv already exists at ${VENV_DIR} — skipping creation."
        else
            echo "  ${YELLOW}⚠ Existing venv at ${VENV_DIR} appears broken (missing python3 or pip). Recreating...${RESET}"
            rm -rf "$VENV_DIR"
        fi
    fi

    if [ ! -d "$VENV_DIR" ]; then
        # Check if python3-venv / ensurepip is available
        if ! python3 -m ensurepip --version >/dev/null 2>&1; then
            local venv_pkg install_cmd_str
            case "$DISTRO_FAMILY" in
                debian)
                    venv_pkg="$(python3 -c "import sys; print(f'python3.{sys.version_info.minor}-venv')")"
                    install_cmd_str="sudo apt install ${venv_pkg}"
                    ;;
                fedora)
                    venv_pkg="python3-virtualenv"
                    install_cmd_str="sudo dnf install ${venv_pkg}"
                    ;;
                arch)
                    venv_pkg="python-virtualenv"
                    install_cmd_str="sudo pacman -S ${venv_pkg}"
                    ;;
                *)
                    venv_pkg="python3-venv"
                    install_cmd_str="# install: ${venv_pkg}"
                    ;;
            esac

            if prompt_yn "  python3-venv is required but not installed. Run '${install_cmd_str}'?" Y; then
                echo "  Installing ${venv_pkg}..."
                if ! eval "$install_cmd_str"; then
                    echo "  ${RED}✗ Failed to install ${venv_pkg}. Cannot create venv.${RESET}"
                    return
                fi
            else
                echo "  Skipping venv creation."
                return
            fi
        fi

        echo "  Creating Python venv at ${VENV_DIR}..."
        if ! python3 -m venv "$VENV_DIR"; then
            echo "  ${RED}✗ Failed to create venv at ${VENV_DIR}.${RESET}"
            return
        fi
        echo "  ${GREEN}✓${RESET} Venv created."
    fi

    echo "  Installing/updating pip dependencies from requirements.txt..."
    if "$VENV_DIR/bin/pip" install -q -r "$REPO_DIR/requirements.txt"; then
        echo "  ${GREEN}✓${RESET} Dependencies installed."
    else
        echo "  ${YELLOW}⚠ pip install encountered errors. System packages may cover the deps.${RESET}"
    fi

    # Write the run wrapper script
    local run_script="$REPO_DIR/htpcstation.sh"
    cat > "$run_script" <<'RUNSCRIPT'
#!/usr/bin/env bash
exec "$(dirname "$0")/venv/bin/python3" "$(dirname "$0")/main.py" "$@"
RUNSCRIPT
    chmod +x "$run_script"
    echo "  ${GREEN}✓${RESET} Run wrapper written: htpcstation.sh"
}

# ── Phase 5: write_config ─────────────────────────────────────────────────────
write_config() {
    echo ""
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo "${BOLD}  Phase 5: Writing Configuration${RESET}"
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""

    # Build JSON booleans
    local tab_retro_json tab_pc_json tab_watch_json tab_listen_json
    if $TAB_RETRO;  then tab_retro_json="true";  else tab_retro_json="false";  fi
    if $TAB_PC;     then tab_pc_json="true";     else tab_pc_json="false";     fi
    if $TAB_WATCH;  then tab_watch_json="true";  else tab_watch_json="false";  fi
    if $TAB_LISTEN; then tab_listen_json="true"; else tab_listen_json="false"; fi

    # plex.server_url only if watch/listen enabled
    local plex_server_url_val=""
    if $TAB_WATCH || $TAB_LISTEN; then
        plex_server_url_val="$PLEX_SERVER_URL"
    fi

    # rom_directory only if retro enabled
    local rom_dir_val=""
    if $TAB_RETRO; then
        rom_dir_val="$ROM_DIR"
    fi

    # Build the config JSON
    local config_json
    config_json=$(cat <<EOF
{
  "plex": {
    "server_url": "${plex_server_url_val}",
    "token": "",
    "server_id": "",
    "user_id": 0,
    "client_id": "",
    "music_library_key": "",
    "player": "mpv"
  },
  "tabs": {
    "show_retro_games": ${tab_retro_json},
    "show_pc_games": ${tab_pc_json},
    "show_watch": ${tab_watch_json},
    "show_listen": ${tab_listen_json}
  },
  "rom_directory": "${rom_dir_val}",
  "retroarch": {
    "command": "flatpak run org.libretro.RetroArch",
    "cores_directory": "~/.var/app/org.libretro.RetroArch/config/retroarch/cores"
  },
  "gamepad": {},
  "theme": {}
}
EOF
)

    echo "  Config that will be written:"
    echo ""
    echo "$config_json" | sed 's/^/    /'
    echo ""

    local do_write=false

    if [ "$EXISTING_CONFIG" = "1" ]; then
        echo "  ${YELLOW}⚠ Existing config found at ${CONFIG_FILE}${RESET}"
        if prompt_yn "  Back up and overwrite?" N; then
            local backup_path="${CONFIG_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
            cp "$CONFIG_FILE" "$backup_path"
            echo "  ${GREEN}✓${RESET} Backed up to ${backup_path}"
            do_write=true
        else
            echo "  Config not written. You can run install.sh again."
            return
        fi
    else
        if prompt_yn "  Write config?" Y; then
            do_write=true
        else
            echo "  Config not written. You can run install.sh again."
            return
        fi
    fi

    if $do_write; then
        mkdir -p "$(dirname "$CONFIG_FILE")"
        printf '%s\n' "$config_json" > "$CONFIG_FILE"
        echo "  ${GREEN}✓${RESET} Config written to ${CONFIG_FILE}"
    fi
}

# ── Phase 6: download_retroarch_cores ────────────────────────────────────────
download_retroarch_cores() {
    echo ""
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo "${BOLD}  Phase 6: RetroArch Core Download${RESET}"
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""

    if ! prompt_yn "  Download recommended RetroArch cores? (~50MB)" N; then
        echo "  Skipping core download."
        return
    fi

    # Check required tools
    if ! check_binary curl; then
        echo "  ${YELLOW}⚠ curl not found — cannot download cores.${RESET}"
        echo "    Install hint: $(install_cmd "curl")"
        return
    fi
    if ! check_binary unzip; then
        echo "  ${YELLOW}⚠ unzip not found — cannot extract cores.${RESET}"
        echo "    Install hint: $(install_cmd "unzip")"
        return
    fi

    local CORES_DIR="$HOME/.var/app/org.libretro.RetroArch/config/retroarch/cores"
    mkdir -p "$CORES_DIR"

    local RETROARCH_CORES=(
        gambatte_libretro        # Game Boy / GBC
        mgba_libretro            # GBA
        mesen_libretro           # NES / FDS
        snes9x_libretro          # SNES
        mupen64plus_next_libretro # N64
        melonds_libretro         # NDS
        genesis_plus_gx_libretro # Mega Drive / Sega CD / Master System / Game Gear
        picodrive_libretro       # 32X
        mednafen_psx_hw_libretro # PS1
        mednafen_pce_libretro    # PC Engine / TurboGrafx
        mednafen_ngp_libretro    # Neo Geo Pocket
        mednafen_wswan_libretro  # WonderSwan
        mednafen_saturn_libretro # Saturn
        flycast_libretro         # Dreamcast / NAOMI
        fbneo_libretro           # Neo Geo / FBNeo arcade
        ppsspp_libretro          # PSP
        pcsx2_libretro           # PS2
        vice_x64_libretro        # C64
        bluemsx_libretro         # MSX / ColecoVision
        fuse_libretro            # ZX Spectrum
        dosbox_pure_libretro     # DOS
        scummvm_libretro         # ScummVM
    )

    local FAILED_CORES=()
    local installed_count=0
    local skipped_count=0

    for core in "${RETROARCH_CORES[@]}"; do
        if [ -f "${CORES_DIR}/${core}.so" ]; then
            echo "  ${GREEN}✓${RESET} ${core} (already installed)"
            skipped_count=$((skipped_count + 1))
            continue
        fi

        local zip_url="https://buildbot.libretro.com/nightly/linux/x86_64/latest/${core}.so.zip"
        local zip_tmp="/tmp/${core}.so.zip"

        if ! curl -fsSL --retry 2 --retry-delay 1 "$zip_url" -o "$zip_tmp" 2>/dev/null; then
            echo "  ${RED}✗${RESET} ${core} (download failed)"
            FAILED_CORES+=("$core")
            continue
        fi

        if ! unzip -q -o "$zip_tmp" "${core}.so" -d "$CORES_DIR" 2>/dev/null; then
            echo "  ${RED}✗${RESET} ${core} (unzip failed)"
            FAILED_CORES+=("$core")
            rm -f "$zip_tmp"
            continue
        fi

        rm -f "$zip_tmp"
        echo "  ${GREEN}✓${RESET} ${core}"
        installed_count=$((installed_count + 1))
    done

    echo ""
    echo "  Cores installed: ${installed_count}  skipped (already present): ${skipped_count}  failed: ${#FAILED_CORES[@]}"

    if [ "${#FAILED_CORES[@]}" -gt 0 ]; then
        echo "  ${YELLOW}⚠ The following cores failed to download/extract:${RESET}"
        for failed in "${FAILED_CORES[@]}"; do
            echo "    ${YELLOW}• ${failed}${RESET}"
        done
    fi
}

# ── Phase 7: download_retroarch_cores_additional ─────────────────────────────
download_retroarch_cores_additional() {
    echo ""
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo "${BOLD}  Phase 7: Additional RetroArch Cores${RESET}"
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
    echo "  Alternative cores for systems already covered, plus less common systems."
    echo "  Includes: bsnes-HD (SNES widescreen), alternative NES/GBA/PS1 cores,"
    echo "  Atari, Amiga, additional Commodore, arcade alternatives, and more."
    echo ""

    if ! prompt_yn "  Download additional RetroArch cores? (~34MB)" N; then
        echo "  Skipping additional core download."
        return
    fi

    # Check required tools (may have been checked in Phase 6, but Phase 6 is optional)
    if ! check_binary curl; then
        echo "  ${YELLOW}⚠ curl not found — cannot download cores.${RESET}"
        echo "    Install hint: $(install_cmd "curl")"
        return
    fi
    if ! check_binary unzip; then
        echo "  ${YELLOW}⚠ unzip not found — cannot extract cores.${RESET}"
        echo "    Install hint: $(install_cmd "unzip")"
        return
    fi

    local CORES_DIR="$HOME/.var/app/org.libretro.RetroArch/config/retroarch/cores"
    mkdir -p "$CORES_DIR"

    local ADDITIONAL_CORES=(
        bsnes_hd_beta_libretro   # SNES — bsnes-HD (widescreen hack support)
        bsnes_libretro           # SNES — bsnes accuracy
        mesen-s_libretro         # SNES — Mesen-S
        snes9x2010_libretro      # SNES — snes9x 2010 (performance)
        nestopia_libretro        # NES — Nestopia
        fceumm_libretro          # NES — FCEUmm
        quicknes_libretro        # NES — QuickNES (performance)
        mgba_libretro            # GBA — mGBA (if not in recommended set)
        sameboy_libretro         # GB/GBC — SameBoy
        gpsp_libretro            # GBA — gpSP (performance)
        vba_next_libretro        # GBA — VBA Next
        tgbdual_libretro         # GB — TGB Dual (link cable)
        parallel_n64_libretro    # N64 — ParaLLEl (Vulkan)
        desmume_libretro         # NDS — DeSmuME
        desmume2015_libretro     # NDS — DeSmuME 2015 (performance)
        pcsx_rearmed_libretro    # PS1 — PCSX ReARMed (performance)
        mednafen_psx_libretro    # PS1 — Mednafen PSX (software)
        swanstation_libretro     # PS1 — SwanStation (DuckStation fork)
        mednafen_pce_fast_libretro # PC Engine — fast variant
        stella_libretro          # Atari 2600 — Stella
        stella2014_libretro      # Atari 2600 — Stella 2014 (performance)
        handy_libretro           # Atari Lynx — Handy
        mednafen_lynx_libretro   # Atari Lynx — Mednafen
        virtualjaguar_libretro   # Atari Jaguar
        neocd_libretro           # Neo Geo CD
        puae_libretro            # Amiga — PUAE (~7.5MB)
        vice_x64sc_libretro      # C64 — VICE x64sc (accurate)
        vice_x128_libretro       # C128
        vice_xvic_libretro       # VIC-20
        vice_xplus4_libretro     # Plus/4
        vice_xpet_libretro       # PET
        fmsx_libretro            # MSX — fMSX
        gearcoleco_libretro      # ColecoVision — Gearcoleco
        cap32_libretro           # Amstrad CPC — Caprice32
        crocods_libretro         # Amstrad CPC — CrocoDS
        blastem_libretro         # Mega Drive — BlastEm (accuracy)
        yabause_libretro         # Saturn — Yabause
    )

    local FAILED_CORES=()
    local installed_count=0
    local skipped_count=0

    for core in "${ADDITIONAL_CORES[@]}"; do
        if [ -f "${CORES_DIR}/${core}.so" ]; then
            echo "  ${GREEN}✓${RESET} ${core} (already installed)"
            skipped_count=$((skipped_count + 1))
            continue
        fi

        local zip_url="https://buildbot.libretro.com/nightly/linux/x86_64/latest/${core}.so.zip"
        local zip_tmp="/tmp/${core}.so.zip"

        if ! curl -fsSL --retry 2 --retry-delay 1 "$zip_url" -o "$zip_tmp" 2>/dev/null; then
            echo "  ${RED}✗${RESET} ${core} (download failed)"
            FAILED_CORES+=("$core")
            continue
        fi

        if ! unzip -q -o "$zip_tmp" "${core}.so" -d "$CORES_DIR" 2>/dev/null; then
            echo "  ${RED}✗${RESET} ${core} (unzip failed)"
            FAILED_CORES+=("$core")
            rm -f "$zip_tmp"
            continue
        fi

        rm -f "$zip_tmp"
        echo "  ${GREEN}✓${RESET} ${core}"
        installed_count=$((installed_count + 1))
    done

    echo ""
    echo "  Cores installed: ${installed_count}  skipped (already present): ${skipped_count}  failed: ${#FAILED_CORES[@]}"

    if [ "${#FAILED_CORES[@]}" -gt 0 ]; then
        echo "  ${YELLOW}⚠ The following cores failed to download/extract:${RESET}"
        for failed in "${FAILED_CORES[@]}"; do
            echo "    ${YELLOW}• ${failed}${RESET}"
        done
    fi
}

# ── Phase 8: print_summary ────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo "${BOLD}  HTPC Station — Setup Summary${RESET}"
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

    # Distro display name
    local distro_display
    case "$DISTRO_FAMILY" in
        debian)  distro_display="Debian/Ubuntu (debian)" ;;
        fedora)  distro_display="Fedora/RHEL (fedora)" ;;
        arch)    distro_display="Arch Linux (arch)" ;;
        *)       distro_display="Unknown (unknown)" ;;
    esac

    # Graphics display name
    local gpu_display
    case "$GPU_VENDOR" in
        intel)    gpu_display="Intel (onboard)" ;;
        amd)      gpu_display="AMD" ;;
        nvidia)   gpu_display="NVIDIA" ;;
        multiple) gpu_display="Multiple detected" ;;
        other)    gpu_display="Other" ;;
        *)        gpu_display="Unknown" ;;
    esac

    # Session display
    local session_display
    case "$SESSION_TYPE" in
        wayland) session_display="Wayland" ;;
        x11)     session_display="Xorg/X11" ;;
        *)       session_display="$SESSION_TYPE" ;;
    esac

    # Tabs enabled
    local tabs_list=""
    $TAB_RETRO  && tabs_list="${tabs_list:+${tabs_list}, }Retro Games" || true
    $TAB_PC     && tabs_list="${tabs_list:+${tabs_list}, }PC Games"    || true
    $TAB_WATCH  && tabs_list="${tabs_list:+${tabs_list}, }Plex Media"  || true
    $TAB_LISTEN && tabs_list="${tabs_list:+${tabs_list}, }Plex Music"  || true
    [ -z "$tabs_list" ] && tabs_list="(none)" || true

    echo "  OS:           ${distro_display}"
    echo "  Graphics:     ${gpu_display}"
    echo "  Session:      ${session_display}"
    echo "  Python venv:  ${VENV_DIR:-${REPO_DIR:-$(pwd)}/venv}"
    echo ""
    echo "  Tabs enabled: ${tabs_list}"
    if $TAB_RETRO && [ -n "$ROM_DIR" ]; then
        echo "  ROM dir:      ${ROM_DIR}"
    fi
    if $TAB_WATCH || $TAB_LISTEN; then
        echo "  Plex server:  ${PLEX_SERVER_URL}"
    fi
    echo ""
    if [ "$MISSING_DEPS" -gt 0 ]; then
        echo "  Missing deps: ${MISSING_DEPS}"
        for cmd in "${MISSING_DEP_CMDS[@]}"; do
            echo "    ${cmd}"
        done
    else
        echo "  Missing deps: 0"
    fi
    echo ""
    echo "  Next steps:"
    if [ "$MISSING_DEPS" -gt 0 ]; then
        echo "  • Install missing dependencies listed above"
    fi
    echo "  • Launch the app: ./htpcstation.sh"
    echo "  • Sign in to Plex from the Settings tab"
    if $PLEX_PASS; then
        echo "  • Some Plex features require Plex Pass (hardware transcoding)"
    fi
    if $HAS_HDHOMERUN; then
        echo "  • Live TV: HDHomeRun tuner will be auto-detected on the Watch tab"
    fi
    echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "${BOLD}  HTPC Station Installer${RESET}"
    echo ""

    detect_environment
    interview
    check_dependencies
    offer_install_missing
    setup_venv
    write_config
    if $TAB_RETRO && check_flatpak "org.libretro.RetroArch"; then
        download_retroarch_cores
        download_retroarch_cores_additional
    fi
    print_summary
}

main "$@"
