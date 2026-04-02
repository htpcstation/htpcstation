#!/usr/bin/env bash
# Quick dependency check for HTPC Station.
# Checks Python, kernel headers, MPV, VA-API drivers, and Python packages.
# Run this before launching the app to verify your system is ready.

set -euo pipefail

OK="\033[0;32m✓\033[0m"
FAIL="\033[0;31m✗\033[0m"
WARN="\033[0;33m!\033[0m"
errors=0

distro="unknown"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    case "${ID:-}" in
        fedora|rhel|centos|rocky|alma) distro="dnf" ;;
        debian|ubuntu|linuxmint|pop)   distro="apt" ;;
        arch|manjaro|endeavouros)      distro="pacman" ;;
        gentoo)                        distro="emerge" ;;
    esac
    # fallback: check ID_LIKE
    if [ "$distro" = "unknown" ]; then
        case "${ID_LIKE:-}" in
            *fedora*|*rhel*)   distro="dnf" ;;
            *debian*|*ubuntu*) distro="apt" ;;
            *arch*)            distro="pacman" ;;
        esac
    fi
fi

missing_sys=""
missing_pip=""
missing_flatpaks=""

echo "HTPC Station — Dependency Check"
echo "================================"
echo "Checks: Python, kernel headers, MPV, VA-API drivers, Python packages"
echo ""

# --- Python ---
if command -v python3 &>/dev/null; then
    py_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    py_major=$(echo "$py_ver" | cut -d. -f1)
    py_minor=$(echo "$py_ver" | cut -d. -f2)
    if [ "$py_major" -ge 3 ] && [ "$py_minor" -ge 10 ]; then
        echo -e "  $OK  Python $py_ver"
    else
        echo -e "  $FAIL  Python $py_ver (need 3.10+)"
        errors=$((errors + 1))
    fi
else
    echo -e "  $FAIL  Python 3 not found"
    errors=$((errors + 1))
fi

# --- Kernel headers ---
if [ -f /usr/include/linux/input.h ]; then
    echo -e "  $OK  Kernel headers (linux/input.h)"
else
    echo -e "  $FAIL  Kernel headers not found (linux/input.h missing)"
    echo -e "       Install with one of:"
    echo -e "         Fedora/RHEL:   sudo dnf install kernel-headers-\$(uname -r)"
    echo -e "         Debian/Ubuntu: sudo apt-get install linux-headers-\$(uname -r)"
    echo -e "         Arch:          sudo pacman -S kernel-headers"
    echo -e "         Gentoo:        sudo emerge sys-kernel/linux-headers"
    errors=$((errors + 1))
    case "$distro" in
        dnf)     missing_sys="${missing_sys:+$missing_sys }kernel-headers-$(uname -r)" ;;
        apt)     missing_sys="${missing_sys:+$missing_sys }linux-headers-$(uname -r)" ;;
        pacman)  missing_sys="${missing_sys:+$missing_sys }kernel-headers" ;;
        emerge)  missing_sys="${missing_sys:+$missing_sys }sys-kernel/linux-headers" ;;
    esac
fi

# --- Video playback (MPV + VA-API) ---
if command -v mpv &>/dev/null; then
    mpv_ver=$(mpv --version 2>/dev/null | head -1 | awk '{print $2}')
    echo -e "  $OK  mpv $mpv_ver"
else
    echo -e "  $FAIL  mpv not found"
    echo -e "       Install with one of:"
    echo -e "         Fedora/RHEL:   sudo dnf install mpv"
    echo -e "         Debian/Ubuntu: sudo apt-get install mpv"
    echo -e "         Arch:          sudo pacman -S mpv"
    echo -e "         Gentoo:        sudo emerge media-video/mpv"
    errors=$((errors + 1))
    case "$distro" in
        dnf)     missing_sys="${missing_sys:+$missing_sys }mpv" ;;
        apt)     missing_sys="${missing_sys:+$missing_sys }mpv" ;;
        pacman)  missing_sys="${missing_sys:+$missing_sys }mpv" ;;
        emerge)  missing_sys="${missing_sys:+$missing_sys }media-video/mpv" ;;
    esac
fi

if command -v vainfo &>/dev/null; then
    echo -e "  $OK  vainfo (VA-API diagnostic)"
else
    echo -e "  $FAIL  vainfo not found (needed to verify hardware video acceleration)"
    echo -e "       Install with one of:"
    echo -e "         Fedora/RHEL:   sudo dnf install libva-utils"
    echo -e "         Debian/Ubuntu: sudo apt-get install vainfo"
    echo -e "         Arch:          sudo pacman -S libva-utils"
    echo -e "         Gentoo:        sudo emerge media-libs/libva-utils"
    errors=$((errors + 1))
    case "$distro" in
        dnf)     missing_sys="${missing_sys:+$missing_sys }libva-utils" ;;
        apt)     missing_sys="${missing_sys:+$missing_sys }vainfo" ;;
        pacman)  missing_sys="${missing_sys:+$missing_sys }libva-utils" ;;
        emerge)  missing_sys="${missing_sys:+$missing_sys }media-libs/libva-utils" ;;
    esac
fi

# Check for Intel VA-API driver (intel-media-driver for Broadwell+, i965 for older)
# On Fedora, libva-intel-media-driver is the codec-restricted free version — it omits
# H.264/HEVC decode. The full driver (intel-media-driver) requires RPM Fusion.
va_driver_found=0
va_driver_restricted=0

# Check for iHD driver (Broadwell+ / J5005 / 8th gen+)
ihd_paths="/usr/lib64/dri/iHD_drv_video.so /usr/lib/dri/iHD_drv_video.so /usr/lib/x86_64-linux-gnu/dri/iHD_drv_video.so"
for p in $ihd_paths; do
    if [ -f "$p" ]; then
        va_driver_found=1
        # On Fedora, check if this is the codec-restricted free package
        # The RPM Fusion full driver lives in dri-nonfree or dri-freeworld paths
        # The restricted free driver is in the standard dri path only
        if [ "$distro" = "dnf" ] && command -v rpm &>/dev/null; then
            pkg=$(rpm -qf "$p" 2>/dev/null | head -1)
            if echo "$pkg" | grep -q "libva-intel-media-driver"; then
                echo -e "  $WARN  Intel VA-API driver found but codec-restricted (libva-intel-media-driver)"
                echo -e "       H.264/HEVC/AV1 hardware decode is DISABLED — video will stutter."
                echo -e "       Install the full driver from RPM Fusion:"
                echo -e "         sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-\$(rpm -E %fedora).noarch.rpm"
                echo -e "         sudo dnf swap libva-intel-media-driver intel-media-driver --allowerasing"
                va_driver_restricted=1
                errors=$((errors + 1))
            else
                echo -e "  $OK  Intel VA-API driver (iHD / intel-media-driver)"
            fi
        else
            echo -e "  $OK  Intel VA-API driver (iHD)"
        fi
        break
    fi
done

# Check for i965 driver (Ivy Bridge / Haswell)
if [ "$va_driver_found" -eq 0 ]; then
    for p in /usr/lib64/dri/i965_drv_video.so /usr/lib/dri/i965_drv_video.so /usr/lib/x86_64-linux-gnu/dri/i965_drv_video.so; do
        if [ -f "$p" ]; then
            echo -e "  $OK  Intel VA-API driver (i965)"
            va_driver_found=1
            break
        fi
    done
fi

if [ "$va_driver_found" -eq 0 ]; then
    echo -e "  $FAIL  Intel VA-API driver not found (hardware video decode will not work)"
    echo -e "       For Broadwell and newer (J5005, 8th gen+) — requires RPM Fusion on Fedora:"
    echo -e "         Fedora/RHEL:   sudo dnf install intel-media-driver  (from RPM Fusion)"
    echo -e "         Debian/Ubuntu: sudo apt-get install intel-media-va-driver-non-free"
    echo -e "         Arch:          sudo pacman -S intel-media-driver"
    echo -e "       For older Intel (Ivy Bridge, Haswell):"
    echo -e "         Fedora/RHEL:   sudo dnf install libva-intel-driver"
    echo -e "         Debian/Ubuntu: sudo apt-get install i965-va-driver"
    echo -e "         Arch:          sudo pacman -S libva-intel-driver"
    errors=$((errors + 1))
    case "$distro" in
        dnf)     missing_sys="${missing_sys:+$missing_sys }intel-media-driver" ;;
        apt)     missing_sys="${missing_sys:+$missing_sys }intel-media-va-driver-non-free" ;;
        pacman)  missing_sys="${missing_sys:+$missing_sys }intel-media-driver" ;;
    esac
fi

# --- Python packages ---
for pkg in PySide6 evdev requests; do
    if python3 -c "import $pkg" &>/dev/null; then
        echo -e "  $OK  Python package: $pkg"
    else
        echo -e "  $FAIL  Python package: $pkg (not installed — run: pip install $pkg)"
        errors=$((errors + 1))
        missing_pip="${missing_pip:+$missing_pip }$pkg"
    fi
done

echo ""

# --- Flatpak apps (optional) ---
echo "Optional Flatpak apps:"

check_flatpak() {
    local app_id="$1"
    local label="$2"
    if command -v flatpak &>/dev/null && flatpak info "$app_id" &>/dev/null; then
        echo -e "  $OK  $label ($app_id)"
    else
        echo -e "  $WARN  $label not found ($app_id) — needed for $3"
        missing_flatpaks="${missing_flatpaks:+$missing_flatpaks }$app_id"
    fi
}

check_flatpak "org.libretro.RetroArch" "RetroArch" "retro games"
check_flatpak "com.valvesoftware.Steam" "Steam" "PC games"
check_flatpak "com.moonlight_stream.Moonlight" "Moonlight" "game streaming"
check_flatpak "com.brave.Browser" "Brave" "Plex playback"

echo ""

# --- Gamepad ---
if ls /dev/input/event* &>/dev/null; then
    echo -e "  $OK  Input devices found in /dev/input/"
else
    echo -e "  $WARN  No input devices in /dev/input/ — gamepad may not work"
fi

echo ""

# --- Summary ---
if [ "$errors" -eq 0 ] && [ -z "$missing_flatpaks" ]; then
    echo "All required dependencies are installed. You're ready to run HTPC Station."
    echo ""
    echo "  python3 main.py"
elif [ "$errors" -eq 0 ] && [ -n "$missing_flatpaks" ]; then
    echo "All required dependencies are installed. You're ready to run HTPC Station."
    echo ""
    echo "  python3 main.py"
    echo ""
    echo "Run this to install optional Flatpak apps:"
    echo ""
    echo "  flatpak install -y flathub $missing_flatpaks"
else
    echo "$errors required dependency issue(s) found. Please fix them before running."
    echo ""

    # Build required one-liner
    req_cmd=""
    if [ -n "$missing_sys" ] && [ "$distro" != "unknown" ]; then
        case "$distro" in
            dnf)     req_cmd="sudo dnf install -y $missing_sys" ;;
            apt)     req_cmd="sudo apt-get install -y $missing_sys" ;;
            pacman)  req_cmd="sudo pacman -S --noconfirm $missing_sys" ;;
            emerge)  req_cmd="sudo emerge $missing_sys" ;;
        esac
    fi
    if [ -n "$missing_pip" ]; then
        if [ -n "$req_cmd" ]; then
            req_cmd="$req_cmd && pip install $missing_pip"
        else
            req_cmd="pip install $missing_pip"
        fi
    fi
    # If distro unknown and only sys packages missing, req_cmd stays empty —
    # the per-distro hint lines printed above are sufficient.
    if [ -n "$req_cmd" ]; then
        echo "Run this to fix required dependencies:"
        echo ""
        echo "  $req_cmd"
    fi
    # If req_cmd is empty but errors > 0 (e.g. Python version too old, or unknown distro
    # with only sys packages missing), the error count message above is sufficient.

    if [ -n "$missing_flatpaks" ]; then
        echo ""
        echo "Run this to install optional Flatpak apps:"
        echo ""
        echo "  flatpak install -y flathub $missing_flatpaks"
    fi

    exit 1
fi
