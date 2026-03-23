(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Configuration
  // ---------------------------------------------------------------------------
  var DEADZONE = 0.3;
  var AUTO_REPEAT_INITIAL_DELAY_MS = 400;
  var AUTO_REPEAT_INTERVAL_MS = 100;

  // Button index → semantic action name (standard gamepad mapping).
  // NOTE: Buttons 0 and 1 are SWAPPED to match the physical controller wiring:
  //   Physical A (BTN_EAST) → Web API button 1 → "accept"
  //   Physical B (BTN_SOUTH) → Web API button 0 → "cancel"
  var _DEFAULT_BUTTON_MAP = {
    0:  'cancel',
    1:  'accept',
    2:  'contextAction1',
    3:  'contextAction2',
    4:  'leftBumper',
    5:  'rightBumper',
    6:  'leftTrigger',
    7:  'rightTrigger',
    8:  'select',
    9:  'start',
    12: 'up',
    13: 'down',
    14: 'left',
    15: 'right'
  };

  // Default D-pad buttons (receive auto-repeat).
  var _DEFAULT_DPAD_BUTTONS = { 12: true, 13: true, 14: true, 15: true };

  // Default axis index → [negative action, positive action]
  var _DEFAULT_AXIS_MAP = {
    0: ['left', 'right'],  // Left stick horizontal
    1: ['up',   'down']    // Left stick vertical
  };

  // Use the auto-generated mapping if available (set by generated_mapping.js),
  // otherwise fall back to the hardcoded defaults above.
  var _gen = window.__htpcGeneratedMapping || null;
  var BUTTON_MAP = _gen ? _gen.buttons : _DEFAULT_BUTTON_MAP;
  var DPAD_BUTTONS = _gen ? _gen.dpadButtons : _DEFAULT_DPAD_BUTTONS;
  var AXIS_MAP = _gen ? _gen.axes : _DEFAULT_AXIS_MAP;

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  var rafId = null;
  var connectedGamepadCount = 0;

  // Per-button state: { pressed: bool, heldSince: number|null, lastRepeat: number|null }
  var buttonState = {};

  // Per-axis direction state: keyed by "<axisIndex>:<direction>" e.g. "0:left"
  // Value: { active: bool, heldSince: number|null, lastRepeat: number|null }
  var axisState = {};

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  /**
   * Returns the active mapping for the current page.
   * Falls back to a no-op if the mapping system isn't loaded yet.
   */
  function getActiveMapping() {
    if (typeof window.__htpcGamepadGetMapping === 'function') {
      return window.__htpcGamepadGetMapping();
    }
    return { onButton: function () {} };
  }

  /**
   * Dispatch a semantic action to the active mapping.
   */
  function dispatchAction(action) {
    console.log('[HTPC Gamepad] action:', action);
    var mapping = getActiveMapping();
    if (mapping && typeof mapping.onButton === 'function') {
      mapping.onButton(action);
    }
  }

  /**
   * Returns true if the given action name is a directional input that should
   * receive auto-repeat.
   */
  function isDirectional(action) {
    return action === 'up' || action === 'down' || action === 'left' || action === 'right';
  }

  // ---------------------------------------------------------------------------
  // Button processing
  // ---------------------------------------------------------------------------

  // Track whether the Start+Select combo has been fired so we don't also
  // fire the individual start/select actions on the same press.
  var _comboFired = false;

  function processButtons(gamepad, now) {
    var buttons = gamepad.buttons;

    // Combo detection: Start (9) + Select (8) pressed simultaneously → close window.
    var startPressed = buttons[9] && buttons[9].pressed;
    var selectPressed = buttons[8] && buttons[8].pressed;
    if (startPressed && selectPressed) {
      if (!_comboFired) {
        _comboFired = true;
        console.log('[HTPC Gamepad] Start+Select combo → closeWindow');
        dispatchAction('closeWindow');
      }
      // Mark both buttons as pressed in state so their individual rising
      // edges are consumed and won't fire when the combo is released.
      for (var ci = 8; ci <= 9; ci++) {
        if (!buttonState[ci]) {
          buttonState[ci] = { pressed: false, heldSince: null, lastRepeat: null };
        }
        buttonState[ci].pressed = true;
        buttonState[ci].heldSince = now;
      }
      return; // Skip individual button processing this frame
    }
    if (_comboFired && !startPressed && !selectPressed) {
      _comboFired = false; // Reset once both are released
    }

    for (var i = 0; i < buttons.length; i++) {
      if (!(i in BUTTON_MAP)) continue;

      var action = BUTTON_MAP[i];
      var pressed = buttons[i].pressed;
      var state = buttonState[i];

      if (!state) {
        state = { pressed: false, heldSince: null, lastRepeat: null };
        buttonState[i] = state;
      }

      // Suppress individual start/select while combo was active
      if (_comboFired && (i === 8 || i === 9)) {
        state.pressed = pressed;
        continue;
      }

      if (pressed && !state.pressed) {
        // Rising edge — button just pressed
        state.pressed = true;
        state.heldSince = now;
        state.lastRepeat = null;
        dispatchAction(action);
      } else if (!pressed && state.pressed) {
        // Falling edge — button released
        state.pressed = false;
        state.heldSince = null;
        state.lastRepeat = null;
      } else if (pressed && state.pressed) {
        // Button held — check auto-repeat (directional inputs only)
        if (isDirectional(action) || DPAD_BUTTONS[i]) {
          var heldFor = now - state.heldSince;
          if (heldFor >= AUTO_REPEAT_INITIAL_DELAY_MS) {
            var repeatBase = state.lastRepeat !== null ? state.lastRepeat : state.heldSince + AUTO_REPEAT_INITIAL_DELAY_MS;
            if (now - repeatBase >= AUTO_REPEAT_INTERVAL_MS) {
              state.lastRepeat = now;
              dispatchAction(action);
            }
          }
        }
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Axis processing
  // ---------------------------------------------------------------------------

  function processAxes(gamepad, now) {
    var axes = gamepad.axes;
    for (var axisIndex in AXIS_MAP) {
      if (!AXIS_MAP.hasOwnProperty(axisIndex)) continue;
      var idx = parseInt(axisIndex, 10);
      if (idx >= axes.length) continue;

      var value = axes[idx];
      var actions = AXIS_MAP[axisIndex];
      var negAction = actions[0]; // e.g. 'left' or 'up'
      var posAction = actions[1]; // e.g. 'right' or 'down'

      var negKey = axisIndex + ':neg';
      var posKey = axisIndex + ':pos';

      var negActive = value < -DEADZONE;
      var posActive = value > DEADZONE;

      processAxisDirection(negKey, negAction, negActive, now);
      processAxisDirection(posKey, posAction, posActive, now);
    }
  }

  function processAxisDirection(key, action, active, now) {
    var state = axisState[key];
    if (!state) {
      state = { active: false, heldSince: null, lastRepeat: null };
      axisState[key] = state;
    }

    if (active && !state.active) {
      // Rising edge
      state.active = true;
      state.heldSince = now;
      state.lastRepeat = null;
      dispatchAction(action);
    } else if (!active && state.active) {
      // Falling edge
      state.active = false;
      state.heldSince = null;
      state.lastRepeat = null;
    } else if (active && state.active) {
      // Held — auto-repeat (all stick directions are directional)
      var heldFor = now - state.heldSince;
      if (heldFor >= AUTO_REPEAT_INITIAL_DELAY_MS) {
        var repeatBase = state.lastRepeat !== null ? state.lastRepeat : state.heldSince + AUTO_REPEAT_INITIAL_DELAY_MS;
        if (now - repeatBase >= AUTO_REPEAT_INTERVAL_MS) {
          state.lastRepeat = now;
          dispatchAction(action);
        }
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Polling loop
  // ---------------------------------------------------------------------------

  function pollGamepads(timestamp) {
    var gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
    var now = timestamp || performance.now();

    for (var i = 0; i < gamepads.length; i++) {
      var gp = gamepads[i];
      if (!gp || !gp.connected) continue;
      processButtons(gp, now);
      processAxes(gp, now);
    }

    rafId = requestAnimationFrame(pollGamepads);
  }

  function startPolling() {
    if (rafId === null) {
      console.log('[HTPC Gamepad] Starting gamepad polling loop');
      rafId = requestAnimationFrame(pollGamepads);
    }
  }

  function stopPolling() {
    if (rafId !== null) {
      console.log('[HTPC Gamepad] Stopping gamepad polling loop');
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    // Clear state so stale held-state doesn't linger on reconnect
    buttonState = {};
    axisState = {};
  }

  // ---------------------------------------------------------------------------
  // Gamepad connect / disconnect events
  // ---------------------------------------------------------------------------

  window.addEventListener('gamepadconnected', function (event) {
    console.log('[HTPC Gamepad] Gamepad connected:', event.gamepad.id, 'index:', event.gamepad.index);
    connectedGamepadCount++;
    startPolling();
  });

  window.addEventListener('gamepaddisconnected', function (event) {
    console.log('[HTPC Gamepad] Gamepad disconnected:', event.gamepad.id, 'index:', event.gamepad.index);
    connectedGamepadCount = Math.max(0, connectedGamepadCount - 1);
    if (connectedGamepadCount === 0) {
      stopPolling();
    }
  });

  // ---------------------------------------------------------------------------
  // Startup: check for already-connected gamepads
  // ---------------------------------------------------------------------------
  // The gamepadconnected event may have fired before this script loaded (e.g.
  // if the user pressed a button before the page finished loading). Poll once
  // to detect any already-connected gamepads.
  (function checkExistingGamepads() {
    var gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (var i = 0; i < gamepads.length; i++) {
      if (gamepads[i] && gamepads[i].connected) {
        console.log('[HTPC Gamepad] Found already-connected gamepad at startup:', gamepads[i].id);
        connectedGamepadCount++;
      }
    }
    if (connectedGamepadCount > 0) {
      startPolling();
    }
  })();

}());
