pragma Singleton
import QtQuick

QtObject {
    // Background and surface colors
    readonly property color colorBackground: "#1a1a2e"
    readonly property color colorPrimary: "#e94560"
    readonly property color colorSecondary: "#16213e"

    // Text colors
    readonly property color colorText: "#eeeeff"
    readonly property color colorTextDim: "#8888aa"

    // Focus ring
    readonly property color colorFocusRing: "#e94560"

    // Tab indicator
    readonly property color colorTabUnderline: "#e94560"

    // Typography
    readonly property string fontFamily: "Sans"
    readonly property int fontSizeTitle: 36
    readonly property int fontSizeHeading: 24
    readonly property int fontSizeBody: 18
    readonly property int fontSizeSmall: 14

    // Animation durations (ms)
    readonly property int animDurationFast: 150
    readonly property int animDurationNormal: 250

    // Focus ring geometry (design-grid px, before vpx scaling)
    readonly property int focusRingWidth: 3
    readonly property int focusRingRadius: 4
}
