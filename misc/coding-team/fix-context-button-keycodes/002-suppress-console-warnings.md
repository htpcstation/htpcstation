# Task 002 — Suppress VDPAU and undefined-button console warnings

## Context

Two unrelated console warnings appear on every run:

1. **`Failed to open VDPAU backend libvdpau_nvidia.so`** — Qt Multimedia's
   GStreamer/FFmpeg stack probes all VDPAU backends at startup. This machine
   has Intel graphics only; there is no NVIDIA driver. Setting
   `VDPAU_DRIVER=va_gl` redirects the VDPAU loader to the VA-GL bridge and
   suppresses the nvidia probe.

2. **`QML Image: Cannot open: …/undefined-button.png`** (×5) — During the
   initial Repeater render pass in `HomeScreen.qml`, `homeScreen.tabSlugs[index]`
   evaluates to `undefined` before `_initTabs()` has run. The image source
   becomes the literal string `"…/homescreen/undefined-button.png"`, which Qt
   tries to load, fails, and logs. The fallback `Rectangle` renders correctly
   so there is no visual bug — only console noise.

## Objective

Silence both warnings with minimal, targeted changes.

## Scope

### Fix 1 — `main.py`

Add one line alongside the existing `LIBVA_MESSAGING_LEVEL` line (line 15):

```python
os.environ.setdefault("VDPAU_DRIVER", "va_gl")
```

### Fix 2 — `qml/screens/HomeScreen.qml`, line 367

Change the `Image.source` binding from:

```qml
source: settings ? settings.themeDir + "homescreen/" + homeScreen.tabSlugs[index] + "-button.png" : ""
```

to:

```qml
source: (settings && index < homeScreen.tabSlugs.length && homeScreen.tabSlugs[index])
    ? settings.themeDir + "homescreen/" + homeScreen.tabSlugs[index] + "-button.png"
    : ""
```

An empty string `""` is silently ignored by Qt's image loader — no warning is
emitted.

## Non-goals / Later

- Do not re-enable the stderr filter in `main.py`.
- Do not change any other environment variables or QML files.
- Do not alter the fallback `Rectangle` logic.

## Constraints / Caveats

- `VDPAU_DRIVER` must be set before PySide6 is imported (it already will be,
  since both env lines sit above the PySide6 imports).
- The `tabSlugs.length` guard also protects against out-of-bounds access if
  the Repeater model count ever exceeds the slugs array length.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
