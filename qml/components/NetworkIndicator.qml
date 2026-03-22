import QtQuick
import ".."

// Displays a WiFi-style connectivity icon.
// Online: 3 concentric arcs + dot in Theme.colorText.
// Offline: same arcs + dot in Theme.colorTextDim with a diagonal strikethrough
//          line in Theme.colorPrimary.
// Pure display — no focus, no interaction.
Canvas {
    id: indicator

    // Set by the parent — true when the device has internet access.
    property bool online: true

    width: root.vpx(24)
    height: root.vpx(24)

    // No focus or interaction
    focus: false
    activeFocusOnTab: false

    // Redraw whenever the online state or theme colours change.
    onOnlineChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)

        var cx = width / 2
        var cy = height * 0.72   // arc centre sits near the bottom

        var arcColor   = online ? Theme.colorText    : Theme.colorTextDim
        var dotColor   = online ? Theme.colorText    : Theme.colorTextDim
        var lineColor  = Theme.colorPrimary

        var lineWidth  = root.vpx(1.5)
        var dotRadius  = root.vpx(2)

        // ── Dot ──────────────────────────────────────────────────────────────
        ctx.beginPath()
        ctx.arc(cx, cy, dotRadius, 0, Math.PI * 2)
        ctx.fillStyle = dotColor
        ctx.fill()

        // ── Three concentric arcs (small → large) ────────────────────────────
        // Each arc spans 180° centred on the top (from 210° to 330° in standard
        // canvas coordinates, i.e. -π*5/6 to -π/6 measured from the positive
        // x-axis).
        var startAngle = Math.PI * 1.2   // ~216°
        var endAngle   = Math.PI * 1.8   // ~324°  (top-facing arc)

        var radii = [root.vpx(5), root.vpx(9), root.vpx(13)]

        ctx.strokeStyle = arcColor
        ctx.lineWidth   = lineWidth
        ctx.lineCap     = "round"

        for (var i = 0; i < radii.length; i++) {
            ctx.beginPath()
            ctx.arc(cx, cy, radii[i], Math.PI + startAngle - Math.PI, Math.PI + endAngle - Math.PI)
            ctx.stroke()
        }

        // ── Strikethrough line (offline only) ────────────────────────────────
        if (!online) {
            ctx.beginPath()
            ctx.moveTo(root.vpx(3), root.vpx(3))
            ctx.lineTo(width - root.vpx(3), height - root.vpx(3))
            ctx.strokeStyle = lineColor
            ctx.lineWidth   = root.vpx(2)
            ctx.lineCap     = "round"
            ctx.stroke()
        }
    }
}
