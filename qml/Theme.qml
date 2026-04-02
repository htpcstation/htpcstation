pragma Singleton
import QtQuick

QtObject {

    // ── Palette: Dark (default) ───────────────────────────────────────────────
    // These are the only values that change between palettes.
    // All semantic tokens below reference these.

    readonly property color _bg:          "#1a1a2e"   // page background
    readonly property color _surface:     "#16213e"   // card / panel surface
    readonly property color _surfaceHigh: "#0f3460"   // elevated surface (dialogs, overlays)
    readonly property color _accent:      "#e94560"   // primary accent (focus, active, badges)
    readonly property color _textPrimary: "#eeeeff"   // primary text
    readonly property color _textDim:     "#8888aa"   // secondary / hint text
    readonly property color _black:       "#000000"   // absolute black (image placeholders)
    readonly property color _white:       "#ffffff"   // absolute white (overlay text)
    readonly property color _badgeSteam:  "#1a9fff"   // Steam source badge
    readonly property color _badgeMoon:   "#ff8c00"   // Moonlight source badge
    readonly property color _success:     "#44cc88"   // success / recorded state
    readonly property color _error:       "#ff6b6b"   // error / failure state
    readonly property color _amber:       "#e5a00d"   // selected track / amber indicator
    readonly property color _muted:       "#888888"   // unselected / muted indicator
    readonly property color _panelDark:   "#CC0d0d14" // MPV subtitle panel background
    readonly property color _rowHighlight: "#44ffffff"  // MPV subtitle row highlight

    // ── Semantic color tokens ─────────────────────────────────────────────────
    // Use these everywhere in QML. Never reference _palette vars directly.

    // Backgrounds
    readonly property color colorBackground:    _bg
    readonly property color colorSurface:       _surface
    readonly property color colorSurfaceHigh:   _surfaceHigh

    // Accent
    readonly property color colorAccent:        _accent
    // Keep colorPrimary as an alias — widely used, renaming is 4b/4c work
    readonly property color colorPrimary:       _accent

    // Text
    readonly property color colorText:          _textPrimary
    readonly property color colorTextDim:       _textDim
    readonly property color colorTextOnAccent:  _white    // text drawn on accent-colored backgrounds

    // Interactive surfaces
    readonly property color colorFocusRing:     _accent
    readonly property color colorTabUnderline:  _accent
    readonly property color colorHighlight:     Qt.rgba(_accent.r, _accent.g, _accent.b, 0.15)

    // Keep colorSecondary as an alias — widely used, renaming is 4b/4c work
    readonly property color colorSecondary:     _surface

    // Overlays
    readonly property color colorOverlay:       Qt.rgba(0, 0, 0, 0.80)   // toast / modal backdrop
    readonly property color colorOverlayMid:    Qt.rgba(0, 0, 0, 0.50)   // progress bar track
    readonly property color colorOverlayText:   _white                    // text on dark overlays

    // Placeholders
    readonly property color colorImagePlaceholder: _black   // poster / artwork placeholder bg

    // Source badges
    readonly property color colorBadgeSteam:    _badgeSteam
    readonly property color colorBadgeMoonlight: _badgeMoon

    // Status indicators
    readonly property color colorSuccess:       _success   // recorded / success state
    readonly property color colorError:         _error     // error / failure state

    // Media player / subtitle overlay
    readonly property color colorPanelDark:     _panelDark    // MPV subtitle panel background
    readonly property color colorRowHighlight:  _rowHighlight // MPV subtitle row highlight
    readonly property color colorTrackSelected: _amber        // selected track indicator
    readonly property color colorTrackMuted:    _muted        // unselected track indicator

    // ── Typography ────────────────────────────────────────────────────────────
    readonly property string fontFamily:    "Sans"
    readonly property int fontSizeTitle:    36
    readonly property int fontSizeHeading:  24
    readonly property int fontSizeBody:     18
    readonly property int fontSizeSmall:    14

    // ── Animation durations (ms) ──────────────────────────────────────────────
    readonly property int animDurationFast:   150
    readonly property int animDurationNormal: 250

    // ── Focus ring geometry (design-grid px, before vpx scaling) ─────────────
    readonly property int focusRingWidth:  3
    readonly property int focusRingRadius: 4
}
