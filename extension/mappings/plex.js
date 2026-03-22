window.__htpcGamepadMappings = window.__htpcGamepadMappings || {};

window.__htpcGamepadMappings.plex = (function () {
  'use strict';

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
    // for Space and Enter — include them for compatibility.
    if (code === 'Space') {
      opts.keyCode = 32;
      opts.which = 32;
    } else if (code === 'Enter') {
      opts.keyCode = 13;
      opts.which = 13;
    }

    target.dispatchEvent(new KeyboardEvent('keydown', opts));
    target.dispatchEvent(new KeyboardEvent('keyup', opts));
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
   * Returns all interactive elements that are currently visible and have
   * non-zero dimensions.
   */
  function getInteractiveElements() {
    return Array.from(document.querySelectorAll(
      'a[href], button, [role="button"], [role="link"], [tabindex]'
    )).filter(function (el) {
      var rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 &&
             el.offsetParent !== null &&
             !el.disabled;
    });
  }

  // ---------------------------------------------------------------------------
  // Virtual focus cursor — highlight management
  // ---------------------------------------------------------------------------

  /**
   * Remove the highlight class from the currently focused element (if any).
   */
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
    if (currentFocusEl && !document.contains(currentFocusEl)) {
      clearHighlight();
      currentFocusEl = null;
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

  function handlePlayerAction(action) {
    switch (action) {
      case 'accept':
        // Play / Pause
        sendKey(' ', 'Space');
        break;
      case 'cancel':
        // Close player
        sendKey('x', 'KeyX');
        break;
      case 'up':
        // Volume up
        sendKey('ArrowUp', 'ArrowUp');
        break;
      case 'down':
        // Volume down
        sendKey('ArrowDown', 'ArrowDown');
        break;
      case 'left':
        // Seek back 10 s
        sendKey('ArrowLeft', 'ArrowLeft');
        break;
      case 'right':
        // Seek forward 30 s
        sendKey('ArrowRight', 'ArrowRight');
        break;
      case 'contextAction2':
        // Toggle fullscreen (Y button)
        sendKey('f', 'KeyF');
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
        if (currentFocusEl && !document.contains(currentFocusEl)) {
          clearHighlight();
          currentFocusEl = null;
        }
        var target = currentFocusEl;
        if (!target) {
          var els = getInteractiveElements();
          target = els.length ? els[0] : null;
        }
        if (target) {
          target.click();
        }
        break;
      }
      case 'cancel':
        // Back / close modal
        sendKey('Escape', 'Escape');
        break;
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
      if (isPlayerActive()) {
        handlePlayerAction(action);
      } else {
        handleNavAction(action);
      }
    }
  };
}());
