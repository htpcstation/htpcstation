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

# --- VA-API hardware video decode ---
# Detect GPU vendor and generation to recommend the correct driver.
# Strategy: use vainfo to check whether H.264 decode is actually available.
# If vainfo reports no H.264 profile, the driver is missing or codec-restricted.

# Detect GPU vendor from lspci
gpu_vendor="unknown"
gpu_desc=""
if command -v lspci &>/dev/null; then
    gpu_line=$(lspci 2>/dev/null | grep -i "vga\|3d\|display" | head -1)
    gpu_desc="$gpu_line"
    if echo "$gpu_line" | grep -qi "intel"; then
        gpu_vendor="intel"
    elif echo "$gpu_line" | grep -qi "amd\|radeon\|ati"; then
        gpu_vendor="amd"
    elif echo "$gpu_line" | grep -qi "nvidia"; then
        gpu_vendor="nvidia"
    fi
fi

# Detect Intel generation from CPU model (for driver selection)
intel_gen="modern"  # default: Broadwell+ (iHD or Mesa iris)
if [ "$gpu_vendor" = "intel" ] && [ -f /proc/cpuinfo ]; then
    cpu_model=$(grep "model name" /proc/cpuinfo | head -1)
    # Sandy Bridge / Ivy Bridge / Haswell = 2nd/3rd/4th gen = use i965 driver
    if echo "$cpu_model" | grep -qiE "i[357]-[23][0-9]{3}|i[357]-4[0-9]{3}|Celeron.*[BG][0-9]|Pentium.*[BG][0-9]"; then
        intel_gen="legacy"
    fi
fi

# Check if H.264 VA-API decode is actually working
# Use --display drm to avoid hanging on Wayland display negotiation.
# Use timeout to prevent blocking if the DRM device is unavailable.
va_h264_ok=0
va_driver_ok=0
if command -v vainfo &>/dev/null; then
    drm_dev=""
    for d in /dev/dri/renderD128 /dev/dri/renderD129 /dev/dri/card1; do
        [ -e "$d" ] && drm_dev="$d" && break
    done
    if [ -n "$drm_dev" ]; then
        vainfo_out=$(timeout --kill-after=2 5 vainfo --display drm --device "$drm_dev" 2>&1 || true)
    else
        vainfo_out=$(timeout --kill-after=2 5 vainfo 2>&1 || true)
    fi
    if echo "$vainfo_out" | grep -q "VAProfileH264"; then
        va_h264_ok=1
        va_driver_ok=1
        echo -e "  $OK  VA-API hardware decode (H.264 confirmed)"
    elif echo "$vainfo_out" | grep -q "VAProfile"; then
        # Driver loaded but H.264 missing — codec-restricted
        va_driver_ok=1
        echo -e "  $FAIL  VA-API driver loaded but H.264 decode unavailable — video will stutter"
        errors=$((errors + 1))

        if [ "$gpu_vendor" = "intel" ]; then
            # Determine correct fix based on distro and GPU generation
            if [ "$distro" = "dnf" ] && command -v rpm &>/dev/null; then
                # Check which package owns the current driver
                current_pkg=""
                for p in /usr/lib64/dri/iHD_drv_video.so /usr/lib64/dri/i965_drv_video.so \
                          /usr/lib64/dri/iris_drv_video.so /usr/lib64/dri/crocus_drv_video.so; do
                    if [ -f "$p" ]; then
                        current_pkg=$(rpm -qf "$p" 2>/dev/null | head -1)
                        break
                    fi
                done
                # Check if mesa-va-drivers (restricted) is the culprit
                if echo "$current_pkg" | grep -q "^mesa-va-drivers-[0-9]"; then
                    echo -e "       mesa-va-drivers (codec-restricted) is installed."
                    echo -e "       Fix: swap for the RPM Fusion freeworld version:"
                    echo -e ""
                    echo -e "         sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-\$(rpm -E %fedora).noarch.rpm"
                    echo -e "         sudo dnf swap mesa-va-drivers mesa-va-drivers-freeworld --allowerasing"
                    missing_sys="${missing_sys:+$missing_sys }mesa-va-drivers-freeworld"
                elif echo "$current_pkg" | grep -q "libva-intel-media-driver"; then
                    echo -e "       libva-intel-media-driver (codec-restricted) is installed."
                    echo -e "       Fix: install intel-media-driver from RPM Fusion:"
                    echo -e ""
                    echo -e "         sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-\$(rpm -E %fedora).noarch.rpm"
                    echo -e "         sudo dnf swap libva-intel-media-driver intel-media-driver --allowerasing"
                    missing_sys="${missing_sys:+$missing_sys }intel-media-driver"
                else
                    echo -e "       Run: sudo dnf swap mesa-va-drivers mesa-va-drivers-freeworld --allowerasing"
                    missing_sys="${missing_sys:+$missing_sys }mesa-va-drivers-freeworld"
                fi
            elif [ "$distro" = "apt" ]; then
                echo -e "       Fix: sudo apt-get install intel-media-va-driver-non-free"
                missing_sys="${missing_sys:+$missing_sys }intel-media-va-driver-non-free"
            elif [ "$distro" = "pacman" ]; then
                echo -e "       Fix: sudo pacman -S intel-media-driver"
                missing_sys="${missing_sys:+$missing_sys }intel-media-driver"
            fi
        elif [ "$gpu_vendor" = "amd" ]; then
            case "$distro" in
                dnf)    echo -e "       Fix: sudo dnf swap mesa-va-drivers mesa-va-drivers-freeworld --allowerasing" ;;
                apt)    echo -e "       Fix: sudo apt-get install mesa-va-drivers" ;;
                pacman) echo -e "       Fix: sudo pacman -S libva-mesa-driver" ;;
            esac
        fi
    else
        # vainfo ran but no profiles at all — driver not found
        echo -e "  $FAIL  VA-API driver not found — hardware video decode unavailable"
        errors=$((errors + 1))
        if [ "$gpu_vendor" = "intel" ]; then
            if [ "$intel_gen" = "legacy" ]; then
                echo -e "       Install the legacy Intel VA-API driver:"
                case "$distro" in
                    dnf)    echo -e "         sudo dnf install libva-intel-driver"
                            missing_sys="${missing_sys:+$missing_sys }libva-intel-driver" ;;
                    apt)    echo -e "         sudo apt-get install i965-va-driver"
                            missing_sys="${missing_sys:+$missing_sys }i965-va-driver" ;;
                    pacman) echo -e "         sudo pacman -S libva-intel-driver"
                            missing_sys="${missing_sys:+$missing_sys }libva-intel-driver" ;;
                esac
            else
                echo -e "       Install the Intel VA-API driver (requires RPM Fusion on Fedora):"
                case "$distro" in
                    dnf)    echo -e "         sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-\$(rpm -E %fedora).noarch.rpm"
                            echo -e "         sudo dnf swap mesa-va-drivers mesa-va-drivers-freeworld --allowerasing"
                            missing_sys="${missing_sys:+$missing_sys }mesa-va-drivers-freeworld" ;;
                    apt)    echo -e "         sudo apt-get install intel-media-va-driver-non-free"
                            missing_sys="${missing_sys:+$missing_sys }intel-media-va-driver-non-free" ;;
                    pacman) echo -e "         sudo pacman -S intel-media-driver"
                            missing_sys="${missing_sys:+$missing_sys }intel-media-driver" ;;
                esac
            fi
        elif [ "$gpu_vendor" = "amd" ]; then
            echo -e "       Install the AMD VA-API driver:"
            case "$distro" in
                dnf)    echo -e "         sudo dnf swap mesa-va-drivers mesa-va-drivers-freeworld --allowerasing"
                        missing_sys="${missing_sys:+$missing_sys }mesa-va-drivers-freeworld" ;;
                apt)    echo -e "         sudo apt-get install mesa-va-drivers"
                        missing_sys="${missing_sys:+$missing_sys }mesa-va-drivers" ;;
                pacman) echo -e "         sudo pacman -S libva-mesa-driver"
                        missing_sys="${missing_sys:+$missing_sys }libva-mesa-driver" ;;
            esac
        else
            echo -e "       Install the VA-API driver for your GPU vendor."
        fi
    fi
else
    # vainfo not installed — already caught above, but handle gracefully
    echo -e "  $WARN  Cannot check VA-API (vainfo not found)"
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
