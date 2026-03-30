window.__htpcGamepadMappings = window.__htpcGamepadMappings || {};

// TEMP DEBUG: on-screen log overlay
(function () {
  var el = document.getElementById('__htpc-debug');
  if (!el) {
    el = document.createElement('div');
    el.id = '__htpc-debug';
    el.style.cssText = 'position:fixed;top:0;left:0;width:50%;max-height:40%;overflow:auto;' +
      'background:rgba(0,0,0,0.85);color:#0f0;font:11px monospace;z-index:999999;padding:4px;pointer-events:none;';
    document.body.appendChild(el);
  }
  window.__htpcDebug = function (msg) {
    console.log(msg);
    var line = document.createElement('div');
    line.textContent = msg;
    el.appendChild(line);
    // Keep last 30 lines
    while (el.childNodes.length > 30) el.removeChild(el.firstChild);
    el.scrollTop = el.scrollHeight;
  };
}());

window.__htpcGamepadMappings.plex = (function () {
  'use strict';
  var dbg = window.__htpcDebug || function () {};

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  /**
   * Dispatch a keydown + keyup pair on the given target.
   * Includes keyCode/which for React compatibility on Space and Enter.
   */
  function sendKey(key, code, target) {
    target = target || document;
    var opts = { key: key, code: code, bubbles: true, cancelable: true };

    // React (and some legacy handlers) check the deprecated keyCode/which fields
    // for Space, Enter, and Escape — include them for compatibility.
    if (code === 'Space') {
      opts.keyCode = 32;
      opts.which = 32;
    } else if (code === 'Enter') {
      opts.keyCode = 13;
      opts.which = 13;
    } else if (code === 'Escape') {
      opts.keyCode = 27;
      opts.which = 27;
    }

    target.dispatchEvent(new KeyboardEvent('keydown', opts));
    target.dispatchEvent(new KeyboardEvent('keyup', opts));
  }

  /**
   * Simulate a full pointer/mouse event sequence on el, matching what a real
   * left-click produces.  React's delegated event system requires bubbling
   * pointerdown/mousedown events — a bare .click() only fires the click event
   * and misses handlers registered on those earlier events.
   *
   * Sequence: pointerdown → mousedown → pointerup → mouseup → click
   *
   * Uses the element's bounding-rect centre for clientX/clientY because some
   * handlers validate that the pointer position is within the element.
   */
  function simulateClick(el) {
    // Give the element DOM focus first; some handlers require it.
    if (typeof el.focus === 'function') {
      el.focus();
    }

    var rect = el.getBoundingClientRect();
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;

    var pointerOpts = {
      bubbles: true,
      cancelable: true,
      button: 0,
      buttons: 1,
      clientX: cx,
      clientY: cy,
      pointerId: 1,
      pointerType: 'mouse',
      isPrimary: true
    };

    var mouseOpts = {
      bubbles: true,
      cancelable: true,
      button: 0,
      buttons: 1,
      clientX: cx,
      clientY: cy
    };

    el.dispatchEvent(new PointerEvent('pointerdown', pointerOpts));
    el.dispatchEvent(new MouseEvent('mousedown', mouseOpts));

    // Real browsers report buttons: 0 on release events (no buttons held).
    pointerOpts.buttons = 0;
    mouseOpts.buttons = 0;

    el.dispatchEvent(new PointerEvent('pointerup', pointerOpts));
    el.dispatchEvent(new MouseEvent('mouseup', mouseOpts));
    el.dispatchEvent(new MouseEvent('click', mouseOpts));
  }

  // ---------------------------------------------------------------------------
  // Player context detection
  // ---------------------------------------------------------------------------

  /**
   * Returns true when the Plex video player overlay is active.
   * Checks for a visible <video> element first (most reliable), then falls back
   * to Plex-specific player container selectors.
   */
  function isPlayerActive() {
    // A playing (or paused-but-open) video element is the most reliable signal.
    var video = document.querySelector('video');
    if (video && !video.paused) {
      return true;
    }

    // Also treat a visible player container as "active" even when paused,
    // so the user can still use gamepad controls while paused.
    if (document.querySelector('[data-testid="playerContainer"]')) {
      return true;
    }
    if (document.querySelector('[class*="PlayerControls"]')) {
      return true;
    }

    return false;
  }

  // ---------------------------------------------------------------------------
  // Virtual focus cursor — state
  // ---------------------------------------------------------------------------

  var currentFocusEl = null;

  // Last known center coordinates of currentFocusEl.  Used to find a
  // replacement element when the focused element is removed from the DOM
  // (e.g. Plex swaps Repeat/RepeatOne buttons on click).
  var lastFocusCX = 0;
  var lastFocusCY = 0;

  // Stack of previously focused elements.  When 'accept' is pressed, the
  // current focus is pushed before clicking (in case the click opens a new
  // overlay layer).  When 'cancel' closes a layer, the stack is popped to
  // restore focus to the element that opened the layer.
  var focusStack = [];

  // Inject the focus highlight style once.
  (function injectFocusStyle() {
    if (document.getElementById('__htpc-focus-style')) {
      return;
    }
    var style = document.createElement('style');
    style.id = '__htpc-focus-style';
    style.textContent =
      '.__htpc-focus { outline: 3px solid #e5a00d !important; outline-offset: 2px !important; }';
    document.head.appendChild(style);
  }());

  // Auto-select user on the Plex user selection screen.
  // After the user is selected, Plex Web navigates to the home screen and
  // loses the original deep link.  We save the intended destination and
  // re-navigate after the user selection completes.
  (function autoSelectUser() {
    // Extract htpc_user from the URL hash fragment
    var hash = window.location.hash || '';
    var match = hash.match(/[?&]htpc_user=([^&]*)/);
    if (!match) return;

    var targetUser = decodeURIComponent(match[1]);
    console.log('[HTPC Gamepad] Auto-select user:', targetUser);

    // Save the original deep link URL (without the htpc_user param)
    // so we can re-navigate after user selection.
    var originalUrl = window.location.href.replace(/[?&]htpc_user=[^&]*/, '');
    console.log('[HTPC Gamepad] Will navigate to:', originalUrl);

    // Poll for the user selection modal (it may not be in the DOM yet)
    var attempts = 0;
    var maxAttempts = 50; // 5 seconds at 100ms intervals
    var interval = setInterval(function() {
      attempts++;

      var modal = document.querySelector('.user-select-modal');
      if (!modal) {
        if (attempts >= maxAttempts) {
          console.log('[HTPC Gamepad] User selection modal not found, giving up');
          clearInterval(interval);
        }
        return;
      }

      // Find the user tile matching the target username
      var userItems = modal.querySelectorAll('.user-select-list-item');
      for (var i = 0; i < userItems.length; i++) {
        var usernameEl = userItems[i].querySelector('.username');
        if (usernameEl && usernameEl.textContent.trim() === targetUser) {
          var link = userItems[i].querySelector('a.user-select-container');
          if (link) {
            console.log('[HTPC Gamepad] Clicking user:', targetUser);
            link.click();
            clearInterval(interval);

            // After user selection, Plex Web redirects to the home screen.
            // Wait briefly for the transition, then navigate to the original
            // deep link URL.
            setTimeout(function() {
              console.log('[HTPC Gamepad] Re-navigating to:', originalUrl);
              window.location.href = originalUrl;
            }, 1500);
            return;
          }
        }
      }

      if (attempts >= maxAttempts) {
        console.log('[HTPC Gamepad] Target user not found in modal:', targetUser);
        clearInterval(interval);
      }
    }, 100);
  }());

  // Auto-click the Play/Resume button on the Plex details page when
  // autoPlay=1 is present in the URL.  Polls for the button since the
  // page is a React SPA and the button may not exist immediately.
  //
  // This is triggered both on initial page load AND on hash changes
  // (e.g. after the auto-user-select re-navigation).
  function tryAutoPlay() {
    var hash = window.location.hash || '';
    if (hash.indexOf('autoPlay=1') === -1) return;

    // Don't auto-play if we're about to do a user selection redirect
    if (hash.indexOf('htpc_user=') !== -1) return;

    console.log('[HTPC Gamepad] Auto-play enabled, waiting for Play button...');

    var attempts = 0;
    var maxAttempts = 100; // 10 seconds at 100ms intervals
    var interval = setInterval(function() {
      attempts++;

      var playBtn = document.querySelector('[data-testid="preplay-play"]');
      if (playBtn) {
        console.log('[HTPC Gamepad] Clicking Play button');
        playBtn.click();
        clearInterval(interval);
        return;
      }

      if (attempts >= maxAttempts) {
        console.log('[HTPC Gamepad] Play button not found, giving up');
        clearInterval(interval);
      }
    }, 100);
  }

  // Run on initial page load
  tryAutoPlay();

  // Also run on hash changes (SPA navigation, e.g. after user selection redirect)
  window.addEventListener('hashchange', function() {
    tryAutoPlay();
  });

  // ---------------------------------------------------------------------------
  // Virtual focus cursor — element discovery
  // ---------------------------------------------------------------------------

  /**
   * Returns the currently open modal/dialog element, or null if none is open.
   * Excludes overlay/backdrop elements to avoid scoping to the wrong container.
   */
  function getActiveModal() {
    return document.querySelector(
      '[role="dialog"], [role="alertdialog"], [data-testid="modal"], ' +
      '[class*="Modal"]:not([class*="ModalOverlay"]):not([class*="Overlay"]), ' +
      '[class*="modal"]:not([class*="modalOverlay"]):not([class*="overlay"])'
    );
  }

  /**
   * Returns the currently open player popup panel element, or null if none is
   * open.  Popup panels (e.g. Playback Settings) are positioned divs floating
   * above the control bar — they are not modals and are not detected by
   * getActiveModal().
   */
  function getActivePopupPanel() {
    var candidate =
      document.querySelector('[data-testid="playbackSettingsContainer"]') ||
      document.querySelector('[class*="AudioVideoStripeContainer"]') ||
      document.querySelector('[class*="AudioVideoPlayQueue-container"]');
    if (!candidate) return null;
    var rect = candidate.getBoundingClientRect();
    return (rect.width > 0 && rect.height > 0) ? candidate : null;
  }

  /**
   * Returns the currently open Popper.js dropdown menu element, or null if
   * none is open.  Plex renders dropdown menus as Popper.js portals inside
   * #modal-root.  Scoped to #modal-root and requires menuitem descendants
   * to avoid false-positives on tooltips or other Popper.js overlays.
   *
   * Applies the same visibility check as getActivePopupPanel().
   */
  function getActiveDropdown() {
    var root = document.getElementById('modal-root');
    if (!root) return null;

    // Look for Popper.js portals inside #modal-root that contain menu items.
    var candidates = root.querySelectorAll(
      '[data-popper-placement], [class*="Menu-menuPortal"]'
    );
    for (var i = 0; i < candidates.length; i++) {
      var candidate = candidates[i];
      // Must contain at least one menuitem to be a real dropdown menu.
      if (!candidate.querySelector('[role="menuitem"]')) continue;
      var rect = candidate.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        return candidate;
      }
    }
    return null;
  }

  /**
   * Returns interactive elements scoped to the player's top bar and bottom
   * control bar only.  Called when the player is active and no modal,
   * dropdown, or popup panel is open.
   *
   * Excludes elements that are not useful for gamepad navigation:
   *   - metadataTitleLink  — navigates away from the player
   *   - mediaDuration      — not an actionable control
   *   - volumeSlider       — volume is controlled via TV/receiver
   */
  function getPlayerNavigableElements() {
    var EXCLUDE_SELECTOR =
      '[data-testid="metadataTitleLink"], [data-testid="mediaDuration"], ' +
      '[class*="volumeSlider"], [class*="VolumeSlider"]';

    var selector = 'button, [role="button"], a[href]';

    var elements = [];

    // Top bar: minimize, close, fullscreen buttons.
    var topBar =
      document.querySelector('[class*="AudioVideoFullPlayer-topBar"]') ||
      document.querySelector('[class*="FullPlayerTopControls"]');
    if (topBar) {
      elements = elements.concat(Array.from(topBar.querySelectorAll(selector)));
    }

    // Bottom control bar: play/pause, skip, settings, etc.
    var controlBar = document.querySelector('[data-testid="playerControlsContainer"]');
    if (controlBar) {
      elements = elements.concat(Array.from(controlBar.querySelectorAll(selector)));
    }

    return elements.filter(function (el) {
      // Exclude non-useful elements.
      if (el.closest(EXCLUDE_SELECTOR)) {
        return false;
      }
      var rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0 || el.disabled) {
        return false;
      }
      // Relax offsetParent check — these bars are absolutely positioned.
      return true;
    });
  }

  /**
   * Returns all interactive elements that are currently visible and have
   * non-zero dimensions.  When a modal, dropdown, or popup panel is open,
   * scopes the search to within that container so background elements are
   * not reachable.  When the player is active (and no overlay is open),
   * scopes to the player's top bar and control bar only.
   *
   * Priority order: modal → dropdown → popup → player (scoped) → document
   */
  function getInteractiveElements() {
    var modal = getActiveModal();
    var dropdown = modal ? null : getActiveDropdown();
    var popup = (modal || dropdown) ? null : getActivePopupPanel();
    var scope = modal || dropdown || popup || document;

    // When the player is active and no overlay is open, restrict navigation
    // to the player's top bar and control bar only.
    if (!modal && !dropdown && !popup && isPlayerActive()) {
      var playerEls = getPlayerNavigableElements();
      if (playerEls.length) {
        return playerEls;
      }
    }

    var selector = 'a[href], button, [role="button"], [role="link"], [tabindex], ' +
                   '[role="menuitem"], [role="option"], [class*="ListItem"], [class*="listItem"]';

    // When scoped to a dropdown, the base selector already covers
    // button[role="menuitem"] items — no extra selector needed.

    // When scoped to a popup panel, also include checkbox inputs and their
    // label click-targets (the <label> is the actual interactive element in
    // Plex's settings rows).
    if (popup) {
      selector += ', input, label[for]';
    }

    return Array.from(scope.querySelectorAll(selector)).filter(function (el) {
      var rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0 || el.disabled) {
        return false;
      }
      // When scoped to a modal, dropdown, or popup panel, relax the
      // offsetParent check because these elements are often
      // position:fixed/absolute and offsetParent is null for such elements.
      if (modal || dropdown || popup) {
        return true;
      }
      return el.offsetParent !== null;
    });
  }

  // ---------------------------------------------------------------------------
  // Virtual focus cursor — highlight management
  // ---------------------------------------------------------------------------

  /**
   * Remove the highlight class from the currently focused element (if any).
   */
  function tryRecoverStaleFocus() {
    // The focused element was removed from the DOM (e.g. React re-render).
    // Try to find a replacement interactive element at the last known position.
    clearHighlight();
    currentFocusEl = null;
    if (lastFocusCX > 0 && lastFocusCY > 0) {
      var hit = document.elementFromPoint(lastFocusCX, lastFocusCY);
      if (hit) {
        var replacement = hit.closest('button, [role="button"], a[href]');
        if (replacement && document.contains(replacement)) {
          var rr = replacement.getBoundingClientRect();
          if (rr.width > 0 && rr.height > 0) {
            setFocus(replacement);
            return;
          }
        }
      }
    }
  }

  function clearHighlight() {
    if (currentFocusEl) {
      currentFocusEl.classList.remove('__htpc-focus');
    }
  }

  /**
   * Apply the highlight class to el and update currentFocusEl.
   * Scrolls the element into view if it is off-screen.
   */
  function setFocus(el) {
    clearHighlight();
    currentFocusEl = el;
    if (el) {
      el.classList.add('__htpc-focus');
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      // Record position so we can find a replacement if the element is
      // later removed from the DOM (e.g. React re-render swaps buttons).
      var r = el.getBoundingClientRect();
      lastFocusCX = r.left + r.width / 2;
      lastFocusCY = r.top + r.height / 2;
    }
  }

  // ---------------------------------------------------------------------------
  // Virtual focus cursor — spatial navigation
  // ---------------------------------------------------------------------------

  /**
   * Given the current element and a direction, find the nearest interactive
   * element in that direction using a distance score that penalises movement
   * on the perpendicular axis (score = deltaMain + deltaPerp * 2).
   *
   * @param {Element} fromEl  — the currently focused element
   * @param {string}  dir     — 'up' | 'down' | 'left' | 'right'
   * @returns {Element|null}
   */
  function findNearest(fromEl, dir) {
    var elements = getInteractiveElements();
    if (!elements.length) {
      return null;
    }

    var fromRect = fromEl.getBoundingClientRect();
    var fromCX = fromRect.left + fromRect.width / 2;
    var fromCY = fromRect.top + fromRect.height / 2;

    var best = null;
    var bestScore = Infinity;

    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      if (el === fromEl) {
        continue;
      }

      var rect = el.getBoundingClientRect();
      var cx = rect.left + rect.width / 2;
      var cy = rect.top + rect.height / 2;

      var dx = cx - fromCX;
      var dy = cy - fromCY;

      // Filter to candidates that are strictly in the requested direction.
      var inDirection = false;
      var deltaMain = 0;
      var deltaPerp = 0;

      switch (dir) {
        case 'right':
          inDirection = dx > 0;
          deltaMain = dx;
          deltaPerp = Math.abs(dy);
          break;
        case 'left':
          inDirection = dx < 0;
          deltaMain = -dx;
          deltaPerp = Math.abs(dy);
          break;
        case 'down':
          inDirection = dy > 0;
          deltaMain = dy;
          deltaPerp = Math.abs(dx);
          break;
        case 'up':
          inDirection = dy < 0;
          deltaMain = -dy;
          deltaPerp = Math.abs(dx);
          break;
      }

      if (!inDirection) {
        continue;
      }

      // Penalise perpendicular offset to prefer same-row / same-column elements.
      var score = deltaMain + deltaPerp * 2;
      if (score < bestScore) {
        bestScore = score;
        best = el;
      }
    }

    return best;
  }

  // ---------------------------------------------------------------------------
  // Virtual focus cursor — D-pad navigation entry point
  // ---------------------------------------------------------------------------

  /**
   * Move the virtual focus cursor in the given direction.
   * On first call (nothing focused), focuses the first interactive element.
   * If the current element has been removed from the DOM, resets and picks first.
   */
  function navigateFocus(dir) {
    var elements = getInteractiveElements();
    if (!elements.length) {
      console.warn('[HTPC Gamepad] No interactive elements found');
      return;
    }

    // Reset if the focused element is no longer in the DOM.
    // Try to find a replacement at the same position first.
    if (currentFocusEl && !document.contains(currentFocusEl)) {
      tryRecoverStaleFocus();
    }

    // If a modal, dropdown, or popup panel is open and the current focus is
    // outside it, reset focus so the next step will pick the first element
    // inside the container.  Priority: modal → dropdown → popup.
    if (currentFocusEl) {
      var modal = getActiveModal();
      var dropdown = modal ? null : getActiveDropdown();
      var popup = (modal || dropdown) ? null : getActivePopupPanel();
      var container = modal || dropdown || popup;
      if (container && !container.contains(currentFocusEl)) {
        clearHighlight();
        currentFocusEl = null;
      }
    }

    // Nothing focused yet — pick the first element.
    if (!currentFocusEl) {
      setFocus(elements[0]);
      return;
    }

    var next = findNearest(currentFocusEl, dir);
    if (next) {
      setFocus(next);
    }
    // If no candidate found in that direction, stay on the current element.
  }

  // ---------------------------------------------------------------------------
  // Action handlers
  // ---------------------------------------------------------------------------

  /**
   * Show the Plex player controls bar by simulating mouse movement.
   * Plex hides the controls after a few seconds of inactivity.
   */
  function showPlayerControls() {
    var player = document.querySelector(
      '[data-testid="playerContainer"], [class*="PlayerControls"], video'
    );
    if (player) {
      player.dispatchEvent(new MouseEvent('mousemove', { bubbles: true }));
    }
  }

  function handlePlayerAction(action) {
    switch (action) {
      case 'accept':
      case 'cancel':
      case 'up':
      case 'down':
      case 'left':
      case 'right':
        // All navigation and accept/cancel actions use the virtual focus
        // cursor.  This handles player control buttons, popup menus
        // (Playback Settings, Subtitles), and any other interactive
        // elements visible on screen.  Show the controls bar first so
        // the buttons are discoverable — but only when no popup/dropdown is
        // open, because the mousemove could cause Plex to dismiss an open
        // dropdown or popup.
        if (!getActivePopupPanel() && !getActiveDropdown()) {
          showPlayerControls();
        }
        handleNavAction(action);
        break;
      case 'leftTrigger':
        // Seek back 10 s
        sendKey('ArrowLeft', 'ArrowLeft');
        break;
      case 'rightTrigger':
        // Seek forward 30 s
        sendKey('ArrowRight', 'ArrowRight');
        break;
      case 'contextAction2':
        // Toggle fullscreen (Y button)
        sendKey('f', 'KeyF');
        break;
      case 'contextAction1':
        // Play / Pause (X button — convenient since A is used for focus click)
        sendKey(' ', 'Space');
        break;
      case 'start':
        window.close();
        break;
      default:
        // Unmapped action — ignore
        break;
    }
  }

  function handleNavAction(action) {
    switch (action) {
      case 'accept': {
        // Reset if the focused element has been removed from the DOM.
        // Try to find a replacement at the same position first.
        if (currentFocusEl && !document.contains(currentFocusEl)) {
          tryRecoverStaleFocus();
        }
        var target = currentFocusEl;
        if (!target) {
          var els = getInteractiveElements();
          target = els.length ? els[0] : null;
        }
        if (target) {
          // Only push to the focus stack when the click is likely to open a
          // new overlay layer.  Elements with aria-haspopup or known trigger
          // buttons (Settings, Chapters, More Actions) open overlays;
          // everything else (chapter items, quality selections, etc.) does
          // not and should not pollute the stack.
          var shouldPush = target.hasAttribute('aria-haspopup') ||
              !!target.closest('[data-testid="videoSettingsButton"], ' +
                             '[data-testid="chaptersButton"], ' +
                             '[data-testid="playQueueButton"], ' +
                             '[data-testid="moreButton"]');
          dbg('accept: push=' + shouldPush +
            ' target=' + target.tagName + '.' + (target.getAttribute('data-testid') || target.getAttribute('aria-label') || target.className.split(' ')[0]));
          if (shouldPush) {
            focusStack.push(target);
          }
          simulateClick(target);

          // After clicking, the target may have been replaced by Plex
          // (e.g. Repeat swaps repeatButton/repeatOneButton via React
          // re-render).  Try to recover focus to the replacement element.
          if (!document.contains(target)) {
            tryRecoverStaleFocus();
          }
        }
        break;
      }
      case 'cancel': {
        // Layered cancel/back behavior — close the topmost layer first.
        // Escape must be dispatched on the overlay element (or a focused
        // element within it) — Plex's menu handlers listen on the menu
        // container, not on document.

        // Helper: restore focus to the element that was focused before the
        // current layer was opened (popped from focusStack).  If the saved
        // element is no longer in the DOM or not visible, clear focus so the
        // next D-pad press picks the first element in the current scope.
        function restorePreviousFocus() {
          clearHighlight();
          currentFocusEl = null;
          while (focusStack.length) {
            var prev = focusStack.pop();
            var inDom = prev && document.contains(prev);
            var visible = false;
            if (inDom) {
              var r = prev.getBoundingClientRect();
              visible = r.width > 0 && r.height > 0;
            }
            dbg('restoreFocus: popped=' +
              (prev ? prev.tagName + '.' + (prev.getAttribute('data-testid') || prev.getAttribute('aria-label') || prev.className.split(' ')[0]) : 'null') +
              ' inDom=' + inDom + ' visible=' + visible);
            if (inDom && visible) {
              setFocus(prev);
              return;
            }
          }
          dbg('restoreFocus: stack empty, no focus restored');
        }

        dbg('cancel: dropdown=' + !!getActiveDropdown() +
          ' popup=' + !!getActivePopupPanel() +
          ' stackLen=' + focusStack.length +
          ' stack=' + focusStack.map(function(el) { return el.tagName + '.' + (el.getAttribute('data-testid') || el.getAttribute('aria-label') || el.className.split(' ')[0]); }).join(' > '));

        var cancelDropdown = getActiveDropdown();
        if (cancelDropdown) {
          // Dispatch Escape on the dropdown itself so Plex's menu handler
          // receives it.  Try the focused element first (if inside the
          // dropdown), then fall back to the dropdown container.
          var escTarget = (currentFocusEl && cancelDropdown.contains(currentFocusEl))
            ? currentFocusEl : cancelDropdown;
          sendKey('Escape', 'Escape', escTarget);
          restorePreviousFocus();
        } else if (getActivePopupPanel()) {
          // Identify which popup panel is open so we can use the correct
          // toggle button as a fallback if Escape doesn't close it.
          var popupPanel = getActivePopupPanel();
          var isPlaybackSettings = !!popupPanel.querySelector('[data-testid="playbackSettingsContainer"]') ||
            !!document.querySelector('[data-testid="playbackSettingsContainer"]');
          var popupEscTarget = (currentFocusEl && popupPanel.contains(currentFocusEl))
            ? currentFocusEl : popupPanel;
          sendKey('Escape', 'Escape', popupEscTarget);

          // Determine which button to click as fallback to toggle the panel.
          var isPlayQueue = popupPanel.matches('[class*="PlayQueue"]') ||
            !!popupPanel.querySelector('[class*="PlayQueue"]');
          var fallbackTestId = isPlaybackSettings ? 'videoSettingsButton' :
            isPlayQueue ? 'playQueueButton' : 'chaptersButton';

          // Give Plex a moment to react; if the panel is still open, toggle it.
          setTimeout(function () {
            var stillOpen = getActivePopupPanel();
            dbg('popup fallback: stillOpen=' + !!stillOpen + ' fallbackBtn=' + fallbackTestId);
            if (stillOpen) {
              var toggleBtn = document.querySelector('[data-testid="' + fallbackTestId + '"]');
              if (toggleBtn) {
                simulateClick(toggleBtn);
              }
            }
          }, 150);
          restorePreviousFocus();
        } else {
          // Modal or no overlay — try close button first, then Escape.
          var cancelModal = getActiveModal();
          if (cancelModal) {
            var closeBtn = cancelModal.querySelector(
              '[aria-label="Close"], [data-testid="modal-close"], ' +
              'button[class*="close"], button[class*="Close"]'
            );
            if (closeBtn) {
              simulateClick(closeBtn);
              clearHighlight();
              currentFocusEl = null;
              break;
            }
          }
          // Fall back to Escape key (closes modal or navigates back).
          sendKey('Escape', 'Escape');
        }
        break;
      }
      case 'up':
        navigateFocus('up');
        break;
      case 'down':
        navigateFocus('down');
        break;
      case 'left':
        navigateFocus('left');
        break;
      case 'right':
        navigateFocus('right');
        break;
      case 'start':
        window.close();
        break;
      default:
        // Unmapped action — ignore
        break;
    }
  }

  // ---------------------------------------------------------------------------
  // Public mapping object
  // ---------------------------------------------------------------------------

  return {
    onButton: function (action) {
      // Start+Select combo closes the browser window from any context.
      if (action === 'closeWindow') {
        window.close();
        return;
      }

      // Routing priority: modal → dropdown → popup → player → nav
      //
      // Modals take priority over the player — navigate the modal with the
      // virtual focus cursor even if the player is loaded behind it.
      // Dropdowns (Popper.js portals) take priority over popup panels so D-pad
      // navigates within the open dropdown.
      // Popup panels (e.g. Playback Settings) take priority over player
      // actions so D-pad navigates within the panel rather than triggering
      // player-mode actions (like showing/hiding controls).
      if (getActiveModal()) {
        handleNavAction(action);
      } else if (getActiveDropdown()) {
        handleNavAction(action);
      } else if (getActivePopupPanel()) {
        handleNavAction(action);
      } else if (isPlayerActive()) {
        handlePlayerAction(action);
      } else {
        handleNavAction(action);
      }
    }
  };
}());
