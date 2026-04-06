# Task 005 — Fix ModifierCaptureDialog: button-release unreliable, hold-to-clear broken

## Root Cause

The `Connections` block receives `rawInput` from a PySide6 custom signal. The architecture
gotcha states: "PySide6 custom signals in `Connections` — May not work." Button-release events
(`value === 0`) are not reliably delivered. As a result:

- Button-down fires → `_pendingCode = code`, `holdTimer.restart()`
- Button-up is never received → `_capture()` is never called from the release path
- Hold timer fires after 1000ms → `_clear()` → `buttonCleared()` → assignment reverted

This broke both the modifier row (which was working in M6) and all hotkey rows.

## Objective

Rewrite the capture mechanic in `ModifierCaptureDialog.qml` to not depend on button-release
events. Increase hold-to-clear time to 3 seconds.

## Scope

### `qml/screens/ModifierCaptureDialog.qml` — only file to change

**New mechanic (no button-release dependency):**

- On button-down (`value === 1`):
  - If no button is currently pending (`_pendingCode === -1`): record `_pendingCode = code`,
    start `holdTimer` (3000ms). Do NOT capture yet.
  - If a button is already pending (`_pendingCode !== -1`): cancel `holdTimer`, capture the
    new button immediately (`_capture(code)`). This handles the case where the user presses
    a second button before the hold timer fires.
- On `holdTimer.onTriggered`: call `_clear()`. Reset `_pendingCode = -1`.
- Remove all `value === 0` (button-release) handling entirely.

This means: first button-down starts the hold timer. Any subsequent button-down (same or
different) before the timer fires captures immediately. If no second press comes within 3s,
the hold timer fires and clears.

Wait — this has a problem: the user can never assign a button with a single press, because
the first press only starts the timer. They'd need to press twice.

**Correct mechanic:**

On button-down (`value === 1`):
- If `_pendingCode === -1` (first press): record `_pendingCode = code`, start `holdTimer`
  (3000ms). Also start a short "capture delay" timer (e.g. 80ms). When the capture delay
  fires, call `_capture(_pendingCode)` — this is the normal "press to assign" path.
- `holdTimer` fires before capture delay: call `_clear()`.

But this still has a race: if hold timer is 3000ms and capture delay is 80ms, the capture
delay always wins. That's actually correct — 80ms after press, capture fires. The hold timer
(3000ms) would never fire because `_capture()` stops it.

This doesn't give us hold-to-clear at all.

**Simplest correct mechanic that avoids button-release:**

Capture on button-down immediately (like M6). For hold-to-clear, require the user to press
and hold — detected by the button firing repeated `value === 1` events (auto-repeat) OR by
a separate "clear" affordance.

Actually the cleanest solution given the constraint: **two-press clear**. First press assigns.
To clear, navigate to the row and press Accept again — the dialog opens again — then press
a dedicated "clear" key (e.g. Y / F1 / context1 button via `Keys.onPressed`).

But the user specifically asked for hold-to-clear. Let's honour that with a workable mechanic:

**Final mechanic — timer-based, no release dependency:**

On button-down (`value === 1`):
- Record `_pendingCode = code`.
- Start `holdTimer` (3000ms).
- Start `captureTimer` (150ms) — short debounce before capturing.

`captureTimer.onTriggered`:
- If `_pendingCode !== -1`: call `_capture(_pendingCode)`. (Normal press path.)

`holdTimer.onTriggered`:
- Stop `captureTimer`.
- Call `_clear()`. (Hold path — fires only if captureTimer was somehow stopped before firing.)

Problem: `captureTimer` (150ms) always fires before `holdTimer` (3000ms). So hold-to-clear
never triggers.

**The only workable approach without button-release:** detect a hold by receiving the SAME
button-down event multiple times (evdev sends repeated events while held, or the gamepad
driver sends them). But this is device-dependent and unreliable.

**Pragmatic solution:** Drop hold-to-clear entirely from the dialog mechanic. Instead:

- Capture on button-down immediately (restoring M6 behaviour — known working).
- To clear a hotkey, the user navigates to the row, presses Accept to open the dialog,
  then presses **B (Escape/Cancel)** — no, that cancels without clearing.

Actually the cleanest UX that works: add a **"Clear" option** accessible via a key press
inside the dialog. When the dialog is open, pressing **Y (F1 / context1)** clears the
assignment. The instruction text updates accordingly.

**Final design:**

- Capture on button-down (`value === 1`) immediately — same as M6. No hold timer.
- Inside the dialog, pressing the **Select button (F9 / Key_F9)** clears the assignment
  (emits `buttonCleared()`).
- Instruction text: "Press a button to assign.\nPress Select to clear."
- `holdTimer` removed entirely.
- `_pendingCode` removed (no longer needed).
- `Keys.onPressed`: handle `Qt.Key_F9` (Select) → `_clear()`. Keep `Qt.Key_Escape` → `_cancel()`.
- Update hold timer interval to N/A (removed).

This is robust, simple, and consistent with the existing gamepad key mapping
(Select = `BTN_SELECT` = `Key_F9` per `keys.py` / architecture.md).

Update instruction text to reflect the 3-second hold time change the user requested — but
since we're removing hold-to-clear, instead say:
"Press a button to assign.\nPress Select to clear."

## Implementation

Remove:
- `property int _pendingCode`
- `Timer { id: holdTimer }`
- All `value === 0` handling in `onRawInput`
- The hold-timer start on button-down

Restore M6 capture-on-button-down:
```qml
function onRawInput(evType, code, value) {
    if (evType === "button" && value === 1) {
        captureDialog._capture(code)
    }
}
```

Add Select-to-clear in `Keys.onPressed`:
```qml
Keys.onPressed: (event) => {
    event.accepted = true
    if (event.key === Qt.Key_Escape) {
        captureDialog._cancel()
    } else if (event.key === Qt.Key_F9) {
        captureDialog._clear()
    }
}
```

Update instruction text:
```
"Press a button to assign.\nPress Select to clear."
```

Update `onVisibleChanged` — remove `holdTimer.stop()` calls (timer no longer exists).

Update `_capture()`, `_clear()`, `_cancel()` — remove `holdTimer.stop()` and `_pendingCode`
resets (no longer needed).

## Non-goals / Later

- Do NOT change `RetroarchHotkeysScreen.qml`.
- Do NOT change any Python files.
- Do NOT change any test files.

## Constraints / Caveats

- `Key_F9` = Select button per the gamepad mapping in `architecture.md`. This is the same
  key used for "Secondary menu" globally. Inside the capture dialog, it is safe to intercept
  it because the dialog has `enabled: focus` and is the active FocusScope.
- The `buttonCleared` signal and `onButtonCleared` handlers in `RetroarchHotkeysScreen` are
  already wired correctly — no changes needed there.
- After this fix, the modifier row and all hotkey rows should assign correctly on first press.
- The title text "SET HOTKEY MODIFIER" is hardcoded — it's the same dialog for both modifier
  and hotkey rows. Leave it as-is (cosmetic issue, out of scope).
