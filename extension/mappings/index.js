function getMapping() {
  var mappings = window.__htpcGamepadMappings || {};

  // Plex Web serves from /web/ (local server) or /desktop/ (app.plex.tv).
  // Match on path rather than hostname so any Plex server IP/hostname works.
  var pathname = window.location.pathname;
  if (pathname.indexOf('/web/') === 0 || pathname.indexOf('/desktop/') === 0) {
    return mappings.plex || { onButton: function() {} };
  }

  // Future: add youtube, netflix, etc.
  return mappings.default || { onButton: function() {} };
}
window.__htpcGamepadGetMapping = getMapping;
