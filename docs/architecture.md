# HTPC Station — Architecture Reference

> Full codebase structure, gotchas, and architecture notes.
> Session-start context: `resume-project.md` | Roadmap: `milestones.md` | History: `changelog.md`

---

## Codebase Structure

```
htpcstation/
  main.py                              # Entry point, PySide6 engine, font loading,
                                       # keyboard/gamepad detection, window hide/show on process launch.
                                       # keys/settings/networkMonitor registered via qmlRegisterSingletonType
                                       # into HTPCBackend 1.0 QML module (BEFORE QQmlApplicationEngine
                                       # is created — PySide6 6.11 requirement). gamepadManager still
                                       # exposed via setContextProperty (assigned post-engine-load).
  pytest.ini                           # testpaths=tests, addopts=-n auto --dist loadfile (pytest-xdist)
  assets/
    fonts/
      NotoEmoji-Regular.ttf            # Bundled emoji font (OFL) — loaded but Qt doesn't reliably use
                                       # it as fallback for all glyphs (see gotchas)
  backend/
    browser_launcher.py                # Brave kiosk launcher, dedicated user-data-dir, extension deploy
    config.py                          # JSON config, ~130 system defaults (all Knulli/Batocera folders),
                                       # all setters auto-save. _write_executor = ThreadPoolExecutor(max_workers=1)
                                       # — Config.save() submits write fire-and-forget (data captured as default arg).
    controller_mapping.py              # Controller mapping config: load/save, dual-record format,
                                       # build_evdev_lookup(), build_web_gamepad_mapping(),
                                       # generate_mapping_js(). Path derived from CONFIG_DIR (imported from config.py).
    gamepad.py                         # evdev → QKeyEvent injection, auto-repeat, hotplug, raw mode,
                                       # startRawMode/stopRawMode (opens/closes SdlResolver),
                                       # getDeviceCapabilities(), setExternalAppActive().
                                       # setup(window, keys) must be called before start() — sets private
                                       # _window/_keys refs used for key injection. start() warns if skipped.
    sdl_resolver.py                    # SdlResolver: ctypes SDL wrapper, probes libSDL2/libSDL3 at
                                       # import, opens SDL joystick on startRawMode, resolves evdev
                                       # events to SDL records via GameControllerDB (compiled into SDL).
                                       # seed_from_controller_mapping() builds primary lookup from saved
                                       # mapping. Module-level singleton: resolver.
    gamelist.py                        # gamelist.xml read/write. ET.indent(getroot(), "  ") applied before
                                       # tree.write() — output is human-readable with 2-space indentation.
                                       # write_game_entry() writes <image> alongside <thumbnail> when
                                       # game.image_path is set. parse_gamelist() returns Game objects with
                                       # path set relative to system_path.
    retro_scraper.py                   # RetroScraper QObject: orchestrates multi-source metadata scraping
                                       # for ROM libraries. Runs in _ScrapeThread (QThread subclass).
                                       # Signals: scrapeProgress(str), scrapeFinished(int, int, int, QVariantMap),
                                       # scrapeError(str), scrapeCancelled(). scrapeFinished carries
                                       # (scraped, skipped, failed, source_counts) where source_counts is a
                                       # dict mapping source name → number of games it contributed metadata for.
                                       # AbstractScraperSource base: _quota_exhausted flag set on 429/430 —
                                       # exhausted sources are skipped for all remaining games in the session.
                                       # _apply_result(game, result, config): sets game.image_path from
                                       # thumbnail (or screenshot if config.scraper_preview_image=="screenshot"),
                                       # only when not already set (preserves user miximages).
                                       # _start_scrape(): truncates scraper.log via handler.stream.seek(0)/
                                       # truncate() before creating _ScrapeThread — each session starts fresh.
                                       # Log: ~/.config/htpcstation/scraper.log
    scrapers/                          # One module per metadata source. All inherit AbstractScraperSource.
      __init__.py
      _utils.py                        # Shared: credential scrubber, URL normaliser, safe_request wrapper
      screenscraper.py                 # ScreenScraper.fr adapter — HTTP 430 = daily quota (sets _quota_exhausted)
      emumovies.py                     # EmuMovies adapter
      thegamesdb.py                    # TheGamesDB adapter
      mobygames.py                     # MobyGames adapter
      igdb.py                          # IGDB adapter (Twitch OAuth)
      retroachievements.py             # RetroAchievements adapter
      hasheous.py                      # Hasheous hash-lookup adapter — correct endpoint:
                                       # GET /api/v1/Lookup/ByHash/md5/{md5} (path param, not query param).
                                       # Response: {"name": "...", "metadata": [{"source": "IGDB", "id": "..."}, ...]}
    keys.py                            # Semantic key abstraction, input source tracking, button layout.
                                       # Registered in QML as HTPCBackend.KeyHandler (not "Keys" —
                                       # that would shadow the built-in QML Keys attached property).
    launcher.py                        # QProcess emulator launcher, async signal-based start
    library.py                         # GameLibrary QObject: models, collections, sort, launch, favorites.
                                       # _scan(): always runs filesystem ROM discovery first, then merges
                                       # gamelist.xml metadata on top. gamelist_games keyed by resolved
                                       # absolute path; fs_games paths also resolved — consistent comparison.
                                       # ROMs not in gamelist.xml get filesystem-only entries (no metadata loss).
    local_video_library.py             # LocalVideoLibrary QObject: flat and TV-shows scanning,
                                       # 5 QAbstractListModel subclasses (CategoryListModel,
                                       # VideoListModel, ShowListModel, SeasonListModel,
                                       # EpisodeListModel), MPV playback, _is_launching guard.
                                       # LocalVideoCache: library.json I/O, poster resolution
                                       # (custom > scraped), metadata merge, tombstone pattern.
                                       # TmdbScraper: TMDb v3 search + poster download, rate-limited
                                       # (0.26s/item). scrapeMovies/scrapeTvShows run on _ScrapeThread
                                       # (QThread subclass, overrides run()); progress routed via
                                       # QMetaObject.invokeMethod trampolines. shutdown() calls
                                       # _scrape_thread.wait() to avoid "QThread destroyed while running".
                                       # Cache dirs: ~/.config/htpcstation/local_videos_cache/
    live_tv_library.py                 # LiveTvLibrary QObject: HDHomeRun guide API fetch, guide cache,
                                       # warm/cold start, background refresh, LiveTvChannelModel
    live_tv_models.py                  # LiveTvChannel dataclass
    metadata_gamelist.py               # GameMetadata dataclass, gamelist.xml reader/writer (Steam + Moonlight)
    models.py                          # Game and System dataclasses
    moonlight_artwork.py               # Artwork cache: Steam Store lookup, CDN download, manual overrides
    moonlight_client.py                # Moonlight CLI wrapper: list_apps(), MoonlightLauncher (QProcess)
    moonlight_config.py                # Shared Moonlight directory helper (~/.config/htpcstation/moonlight/)
    moonlight_library.py               # MoonlightLibrary QObject: two-phase refresh, models, launch
    moonlight_models.py                # MoonlightHost, MoonlightApp dataclasses
    moonlight_parser.py                # Moonlight QSettings config parser, host discovery, TCP probe
    moonlight_play_history.py          # Play timestamp recording/reading (play_history.json)
    recently_played.py                 # RecentlyPlayedManager QObject: cross-category play history,
                                       # persisted to ~/.config/htpcstation/recently_played.json.
                                       # Max 50 entries. De-dups by (source, nav_params). record() slot,
                                       # getRecent() slot (top 5), changed signal. Exposed as
                                       # recentlyPlayed context property. Always called on main thread.
                                       # _write_executor = ThreadPoolExecutor(max_workers=1) — record()
                                       # submits self._save before emitting changed (write is fire-and-forget).
    mpv_launcher.py                    # LibMpvPlayer: python-mpv in-process player, VA-API hwdec,
                                       # Wayland/Xorg auto-detect, programmatic keybinds, property
                                       # observers (time-pos, pause), live TV variant with reconnect options
    network_monitor.py                 # NetworkMonitor QObject: periodic connectivity check, online property
    plex_account.py                    # plex.tv API: OAuth, server discovery, home users, user switching
    plex_client.py                     # Plex Media Server HTTP client, get_stream_url(), report_timeline(),
                                       # persist_stream_selection(), mark_played/unplayed, transient token,
                                       # get_metadata(include_markers=True), get_markers().
                                       # PlexEventListener: SSE library-change listener running in
                                       # _PlexSSEThread (QThread subclass, overrides run()). Created/
                                       # destroyed dynamically as the Plex connection changes.
    plex_library.py                    # PlexLibrary QObject: threaded data loading, models, sort/filter,
                                       # music slots, server/user management, MPV/browser launch,
                                       # My List (plex_cache/plex_mylist.json), subtitle IPC slots,
                                       # timeline reporter wiring, track persistence, skip intro markers,
                                       # fetchStreamInfo async, streamInfoReady signal.
                                       # Disk cache: libraries/ondeck/movies/shows/artists all cached to
                                       # plex_cache/ and loaded at startup via _worker_load_all_caches
                                       # (_cache_executor, dedicated thread). Sort/genre state persisted
                                       # per section key in plex_cache/state.json.
                                       # Sort-on-cache-load: selectLibrary() applies persisted sort to
                                       # movies/shows immediately when loading from disk cache, so content
                                       # appears in the correct order before the server fetch completes.
                                       # Incremental model early-exit: PlexLibraryListModel.set_items(),
                                       # PlexOnDeckModel.set_items(), PlexArtistListModel.set_artists()
                                       # skip beginResetModel/endResetModel when incoming data == current.
    plex_models.py                     # PlexMovie, PlexShow, PlexSeason, PlexEpisode, PlexArtist,
                                       # PlexAlbum, PlexTrack dataclasses
    poster_cache.py                    # Thread-safe poster downloader, SHA256 hash filenames.
                                       # Downloads via /photo/:/transcode at 400px wide (server-side resize).
    retroarch_config.py                # read_cfg/write_cfg, HOTKEY_CFG_KEYS (triple keys per action:
                                       # _btn/_axis/_hat), build_hotkey_cfg() writes correct key type
                                       # from SDL record type (button/axis/hat)
    settings_manager.py                # SettingsManager QObject: wraps Config for QML, OAuth,
                                       # plexPlayer toggle (mpv/browser), RetroArch hotkey slots,
                                       # controller mapping slots, SDL record label resolution.
                                       # Scraper slots: scraperSourceEnabled(source)/setScraperSourceEnabled,
                                       # getScraperCredential(source,key)/setScraperCredential,
                                       # scraperPreviewImage()/setScraperPreviewImage, getRetroSystemsList.
    steam_config.py                    # Shared Steam directory helper (~/.config/htpcstation/steam/)
    steam_library.py                   # SteamLibrary QObject: models, sort, launch, recently played,
                                       # metadata fetch, favorites. GOG-ready source list model.
    steam_metadata.py                  # Steam Store API metadata fetcher (appdetails endpoint)
    steam_models.py                    # SteamGame dataclass
    steam_parser.py                    # ACF/VDF parser, game discovery, artwork resolution + caching
    utils.py                           # Shared utilities: load_json(path) / save_json(path, data, indent) —
                                       # UTF-8 read/write helpers (load returns {} when file absent).
                                       # safe_request(call, context) — catches ConnectionError/Timeout/
                                       # HTTPError, logs warning, returns None. Only for plain network calls
                                       # with no content parsing; plex_account.py needs broader except
                                       # Exception coverage for XML/JSON parse errors and is NOT a target.
  extension/                           # Chromium browser extension (Manifest V3)
    manifest.json
    content.js                         # Gamepad API polling, edge detection, auto-repeat, Start+Select
    generated_mapping.js               # Auto-generated button mapping (written at deploy time)
    mappings/
      default.js                       # No-op fallback for non-Plex sites
      index.js                         # Site matcher
      plex.js                          # Plex Web mapping: player controls, virtual focus cursor,
                                       # popup/dropdown navigation, focus stack, stale focus recovery,
                                       # auto-user-select, auto-play, auto-expand mini player (~900 lines)
  qml/
    main.qml                           # ApplicationWindow, vpx(). QuitDialog and
                                       # ControllerMappingDialog are Loader { active: false } —
                                       # not instantiated until first opened; destroyed on close.
    Theme.qml                          # Singleton: two-layer token system — _palette vars (neutral dark:
                                       # #111111/#1c1c1c/#2a2a2a) + semantic tokens (colorAccent,
                                       # colorSurface, colorOverlay, colorBadgeSteam, etc.). colorPrimary
                                       # and colorSecondary kept as aliases. No hardcoded hex in any other
                                       # QML file. fontFamily: Liberation Sans. colorAccent and
                                       # colorFocusRing are settings-driven (runtime-overridable,
                                       # persisted to config.json ui section). focusScale (1.05) and
                                       # focusScaleDuration (120ms) tokens for delegate animations.
                                       # focusRingRadius: 10. animDurationFast: 80ms (tab fades).
    qmldir                             # Singleton registration
    components/
      ClockDisplay.qml
      FocusRing.qml
      GridCellHighlight.qml              # Focus-tint rectangle for grid delegates. `active` bool property;
                                         # colorPrimary at opacity 0.15 (active) / 0.0 (inactive) with
                                         # animDurationFast Behavior. Use `import ".."` — same convention as FocusRing.
      LibraryHeader.qml                  # Two-Rectangle header shared by all 22 grid/list screen files.
                                         # 56px primary bar (◀ + title) + 28px status bar (statusText, rightText1/2/3).
                                         # Screens anchor content to `header.bottom` directly — do NOT define
                                         # a property alias named `bottom` inside this component; `bottom` is a
                                         # FINAL property of QML's Item and cannot be overridden or aliased.
      LoadingOverlay.qml                 # Full-screen dark overlay (colorBackground) shown only after a
                                         # configurable delay (default: Theme.loadingOverlayDelay = 1000ms).
                                         # MUST import ".." — Theme is registered in qml/qmldir and is only
                                         # accessible via this import. Without it, delay coerces to 0
                                         # (immediate) and color defaults to white, causing a white flash on
                                         # every loading event.
      NetworkIndicator.qml
      QuitDialog.qml
      SettingButton.qml
      SettingSelect.qml
      SettingSlider.qml
      SettingTextInput.qml
      SettingToggle.qml
    screens/
      HomeScreen.qml                   # Two-level launcher: Level 1 = background image + centered image
                                        # buttons (theme-driven); Level 2 = tab content loaded on demand.
                                        # Tab content destroyed on back() to prevent eager network calls.
                                        # MediaPlayer + AudioOutput, global X play/pause, MPV running state,
                                        # subtitle overlay trigger. 80ms opacity fade on tab enter/exit.
                                        # Home icon row at height/4 (25% from top).
                                        # RecentlyPlayedWidget below tab bar; accent-color divider separates
                                        # them. slugMap maps source strings → tab slugs for deep nav.
                                        # onActivated(source, navParams) handles widget card presses.
      RetroGamesScreen.qml             # System list + game grid + detail (3-state)
      GameGridView.qml
      GameDetailView.qml
      GameListView.qml                 # Split-panel list view for retro games
      PcGamesScreen.qml                # Steam source list + game grid + detail (3-state), Steam Favorites
      MoonlightScreen.qml              # Moonlight source list (Recently Played, Favorites, Apps) + app grid + detail
      SteamGameGrid.qml
      SteamGameDetail.qml
      SteamGameList.qml
      MoonlightAppGrid.qml
      MoonlightAppDetail.qml
      MoonlightAppList.qml
      RecentlyPlayedGrid.qml           # Shared recently played / favorites grid (used by PC Games + Moonlight tabs)
      RecentlyPlayedList.qml
      RecentlyPlayedDetail.qml
      WatchScreen.qml                  # Plex library list + movie/show grids + detail + My List + Live TV
                                       # _playContent(): MPV or browser per settings.plexPlayer
                                       # resume dialog (viewOffset > 0)
      PlexMovieGrid.qml
      PlexMovieDetail.qml
      PlexMovieList.qml
      PlexShowGrid.qml
      PlexShowDetail.qml
      PlexShowList.qml
      PlexOnDeckGrid.qml               # Continue Watching / My List grid (configurable model + sourceTitle)
      PlexOnDeckList.qml
      LiveTvScreen.qml                 # Embedded Live TV channel guide
      MpvSubtitleOverlay.qml           # Always-on-top Window for subtitle track selection during MPV
      MpvSkipIntroOverlay.qml          # Always-on-top Window for skip intro button (bottom-right)
      ListenScreen.qml                 # Plex Music: menu, artists, albums, tracks, now playing
      LocalVideosScreen.qml            # 5-view FocusScope: categories → videos/shows → seasons →
                                       # episodes. Lazy scan on selectCategory(). B = back one level.
                                       # navTarget support: "movie" branch constructs _selectedMovieData
                                       # directly from nav_params; "show" branch constructs
                                       # _selectedShowData. No model search — data comes from navTarget.
      RecentlyPlayedWidget.qml         # Horizontal 5-card row below HomeScreen tab bar. Visible in
                                       # launcher state only. Artwork + title per card. Empty state text.
                                       # Down from tab bar → widget; B → back to tab bar; A → deep nav.
      ControllerMappingDialog.qml       # Full-screen wizard: 14 inputs, raw mode, co-firing collection,
                                        # hold-to-skip (skippable actions), Start+Select cancel,
                                        # auto-save on completion
      ModifierCaptureDialog.qml        # Modal overlay: capture one button/axis for hotkey modifier or
                                        # hotkey action; tap to assign, hold 3s to clear; 10s timeout
      RetroarchHotkeysScreen.qml       # Modifier row + 12 interactive hotkey rows + rewind settings +
                                        # Apply button; warns if mapping wizard not yet run
      SystemCoresScreen.qml            # Per-system RetroArch core editor
      SettingsScreen.qml               # Settings menu with tabbed subcategories. Games tab includes
                                       # "Scraping" subcategory group for RetroScraper settings.
                                       # _settingsRevision: int counter — incremented at end of every
                                       # _setValue() call. All 4 delegate value bindings reference
                                       # `settingsScreen._settingsRevision >= 0` so QML re-evaluates
                                       # them reactively. Without this, plain JS function calls in
                                       # bindings are never re-evaluated after initial render.
  tests/
    conftest.py
    test_collections.py                # 22 tests
    test_controller_mapping.py         # 38 tests
    test_auto_mapping.py               # 31 tests
    test_sdl_resolver.py               # 688 tests (SdlResolver, seed_from_controller_mapping, resolve)
    test_retroarch_hotkeys.py          # ~120 tests (RetroarchHotkeysScreen backend slots)
    test_retroarch_config.py           # ~60 tests (read_cfg/write_cfg/build_hotkey_cfg)
    test_emulator_launch.py            # 24 tests
    test_filter_sort.py                # 12 tests
    test_gamelist_parser_fixes.py      # 7 tests
    test_gamelist_fixes_010.py         # 13 tests (ET.indent, image tag, preview image config, _apply_result)
    test_retro_scraper_framework.py    # scraper framework: Config round-trips, quota-exhausted flag,
                                       # Hasheous endpoint + response parsing (md5/crc path params),
                                       # scrapeFinished 4-arg signature
    test_retro_scraper_data_model.py   # ScraperResult / Game data model tests
    test_quota_exhausted.py            # 18 tests (quota flag set on 429/430, skipped on subsequent calls)
    test_rom_fallback_scan.py          # library.py filesystem+gamelist merge: ROMs not in gamelist stay visible
    test_scraper_screenscraper.py      # ScreenScraper adapter (HTTP mocked)
    test_scraper_emumovies.py          # EmuMovies adapter
    test_scraper_thegamesdb.py         # TheGamesDB adapter
    test_scraper_mobygames.py          # MobyGames adapter
    test_scraper_igdb.py               # IGDB adapter
    test_scraper_retroachievements.py  # RetroAchievements adapter
    test_config_save_race.py           # 4 tests (CONFIG_FILE snapshot prevents writes to real config)
    test_live_tv_library.py            # ~38 tests (HDHomeRun guide API)
    test_moonlight_artwork.py          # 36 tests
    test_moonlight_client.py           # 24 tests
    test_moonlight_library.py          # 119 tests
    test_moonlight_parser.py           # 30 tests
    test_moonlight_play_history.py     # 20 tests
    test_mpv_launcher.py               # 45 tests
    test_network_monitor.py            # 13 tests
    test_pc_games_favorites.py         # 58 tests
    test_plex_account.py               # 45 tests
    test_plex_backend.py               # ~600 tests (disk cache, sort/filter, async workers, models)
    test_plex_music.py                 # ~200 tests (artist/album/track/playlist async fetch)
    test_plex_mylist.py                # 36 tests
    test_plex_stream.py                # 15 tests
    test_plex_client.py                # 11 tests (identity headers, timeline, track persistence)
    test_plex_timeline.py              # 10 tests (PlexTimelineReporter lifecycle + push interface)
    test_harden_batch1.py              # ~80 tests (hardening batch)
    test_settings_backend.py           # ~200 tests
    test_steam.py                      # 95 tests
    test_video_snap.py                 # 5 tests
    test_browser_launch.py             # 31 tests
    test_keys.py                       # 17 tests (key code changes: 1/2 replace F1/F2)
    test_gamepad_disconnect.py         # 13 tests (disconnect crash fix, hint flash fix, setup() method)
    test_theme_config.py               # ~226 tests (theme palette, accent/focus ring colors, config persistence)
    test_local_video_config.py         # 28 tests (Config/SettingsManager: local_video_categories, tmdb_api_key)
    test_local_video_cache.py          # 44 tests (LocalVideoCache: load/save, resolve_poster, resolve_metadata,
                                       # tombstone, set_entry merge, _slugify)
    test_local_video_library.py        # 63 tests (scan, models, enrichment, scrape slots)
    test_tmdb_config_cache_paths.py    # 18 tests (tmdb_api_key config round-trip, cache path constants)
    test_tmdb_scraper.py               # 32 tests (TmdbScraper: search_movie, search_tv_show, download_poster,
                                       # scrape_movies, scrape_tv_shows — all HTTP mocked)
    test_recently_played.py            # 21 tests (RecentlyPlayedManager: record, de-dup, getRecent, persist)
    test_hook_launches.py              # 15 tests (record() called on launch for all 6 categories)
    test_plex_section_sort_restore.py  # 19 tests (_SORT_MAP_REVERSE, getSectionSort, getSectionGenre,
                                       # sort applied to cached data on selectLibrary())
```

**Test isolation:** `tests/conftest.py` has two autouse fixtures:
- `isolate_plex_cache` — patches `_PLEX_CACHE_DIR`, `_POSTER_CACHE_DIR`, and `_CACHE_DIR` (live TV) to `tmp_path`; stubs `_migrate_cache_dirs` to a no-op. Tests never touch `~/.config/htpcstation/` at runtime.
- `_mock_sse_thread_run` — patches `_PlexSSEThread.run` to a no-op, preventing real DNS resolution attempts in tests that exercise `PlexLibrary`. Tests that need the real `run()` behaviour (i.e. `TestPlexEventListener`) opt out with `@pytest.mark.real_sse_run`.

**Parallel execution:** `pytest.ini` configures `pytest-xdist` with `-n auto --dist loadfile`. Each file runs in one worker process; Qt singletons are per-process (correct). Suite runtime: ~16-18s.

**Local video cache isolation is NOT covered by `conftest.py`** — `_MOVIES_CACHE_DIR` and
`_TV_SHOWS_CACHE_DIR` are separate module-level constants in `local_video_library.py`. Any
test that exercises `selectCategory()` enrichment or scrape integration with the real cache
paths must `monkeypatch` these constants explicitly (e.g.
`monkeypatch.setattr(lvl, "_MOVIES_CACHE_DIR", tmp_path / "movies")`). Failure to do so
writes and then deletes the user's real `library.json` on every test run.

---

## Architecture Notes

### Theme System
- Themes live in `themes/<name>/` relative to the app root.
- Active theme set via `Config.theme_name` (default: `"default"`), persisted in `config.json` under `"ui"`.
- `SettingsManager.themeName` (str) and `themeDir` (str, `file://` URL ending in `/`) expose the theme to QML.
- `APP_DIR = Path(__file__).parent` defined in `main.py`; passed to `SettingsManager` as `app_dir`.
- Theme assets for the homescreen: `home-background.png` (full-screen background), `<slug>-button.png` per tab (slugs: `retrogames`, `pcgames`, `moonlight`, `plexmedia`, `plexmusic`, `settings`).
- Fallback: if a button image fails to load (`Image.status !== Image.Ready`), a plain rectangle + text label is shown.
- Color palette swap (future 4b/4c work) is separate from the image theme system.
- Two-layer token structure (Theme.qml): `_palette` vars (internal, only these change between color themes) → semantic tokens (what QML files use). Never reference `_palette` vars directly from QML files.

### UI Layout Hierarchy

Every screen follows a three-level layout:

| Level | Height | Contents |
|---|---|---|
| `headerBar` | `vpx(56)` | `◀  Screen Title` (left-aligned). Title only — no hints. |
| `statusBar` | `vpx(28)` | Left: sort/status label. Right: button hints (`anchors.right`, `rightMargin: vpx(16)`). |
| Content area | fills remainder | Grid, list, detail, etc. Top margin `vpx(16)` from `statusBar.bottom`. |

Global status indicators (clock, network, now playing + ▶/■ symbol) live in `HomeScreen.qml`, anchored top-right, z-ordered above all content. The `rightMargin: vpx(16)` on hint Rows keeps hints flush under the indicators.

Button hint conventions:
- Accept (A/Enter) and Cancel (B/Escape) are **never** shown — universally understood.
- Keyboard shortcuts: Context1 = `1`, Context2 = `2`, PageUp/Down = `PgUp`/`PgDn`.
- Gamepad labels use `keys.context1Label`, `keys.context2Label`, etc. — always via the ternary `keys.useGamepadLabels ? ... : ...`.
- Hint text switches reactively via `keys.useGamepadLabels` (set by `Keys.setGamepadInput()` / `Keys.setKeyboardInput()`).

### QML Focus Management
- Every screen/component is a `FocusScope` with `enabled: focus`
- Gamepad events injected as `QKeyEvent`s — QML only sees keyboard events
- `FocusRing.qml` shows on `parent.activeFocus`
- `vpx()` lives on `ApplicationWindow` (id: `root`) — never shadow this id in components

### Threading Model
- All UI on Qt main thread
- Plex API calls via `ThreadPoolExecutor(max_workers=2)` (`self._executor`), results via Qt signals
- Poster downloads via dedicated `ThreadPoolExecutor(max_workers=10)` (`self._poster_executor`) — separate from main executor to avoid blocking library loads
- Moonlight host probing + app enumeration via `ThreadPoolExecutor(max_workers=2)`
- Emulator/browser/Moonlight launch via `QProcess` (async, non-blocking)
- Steam game discovery is synchronous (small local ACF file reads)
- Live TV: HDHomeRun `discover.json` sequential (fast, local), then `lineup.json` + guide API parallel (2 workers)
- `PlexTimelineReporter`: `_TimelineWorker(QObject)` moved to a `QThread` via `moveToThread()` — heartbeat loop uses `_stop_event.wait(timeout)` so `exec()` can process `quit()`. `stop()` calls `thread.quit()` + `thread.wait()`.
- `PlexEventListener` (`plex_client.py`): `_PlexSSEThread(QThread)` subclass overriding `run()` — blocking HTTP/SSE loop. Created fresh each time the Plex connection is established.
- `LocalVideoLibrary` scrape: `_ScrapeThread(QThread)` subclass overriding `run()`. `shutdown()` calls `_scrape_thread.wait()`.
- `mpv_launcher.py` fire-and-forget threads: `threading.Thread` intentionally retained — sub-second lifetime, use `QMetaObject.invokeMethod(QueuedConnection)` to marshal results back to main thread. No Qt event loop required.
- **JSON write executors** — `config.py` and `recently_played.py` each own a module-level `_write_executor = ThreadPoolExecutor(max_workers=1)` for serialised fire-and-forget disk writes. `max_workers=1` prevents race conditions on rapid saves. Pattern matches `_cache_executor` in `plex_library.py`.
- All internal signals that cross thread boundaries use explicit `Qt.ConnectionType.QueuedConnection` — required because `ThreadPoolExecutor` threads are not `QThread` subclasses, so PySide6 `AutoConnection` defaults to `DirectConnection` (not queued)

### Process Lifecycle
- **Emulators/Browser/Moonlight:** `processStarted` → `window.hide()`, `processFinished` → `window.showFullScreen()` + `raise_()` + `requestActivate()`
- **Steam:** No window management — game takes focus, WM handles return on exit
- **MPV:** Same hide/show pattern. `MpvLauncher.processStarted` → `plex.mpvStarted` → `homeScreen._mpvRunning = true`
- **Browser kill:** `GamepadManager.startSelectCombo` → `browser_launcher.kill()` → `flatpak kill <app_id>`

### Plex Architecture
- **`PlexAccount`** — talks to `plex.tv` for OAuth, server discovery, home users, user switching. Old `/api/` endpoints use XML + token as query param. OAuth methods are `@staticmethod`.
- **`PlexClient`** — talks to local media server. Always uses admin token. Sends full identity headers (`X-Plex-Client-Identifier`, `X-Plex-Product`, etc.) on every request. `get_stream_url(ratingKey)` returns `(url, view_offset_ms)`. `report_timeline()` is fire-and-forget (timeout=5s, never raises). `persist_stream_selection()` PUTs audio/subtitle choice with `allParts=1`. `get_transient_token()` returns short-lived delegation token for stream URLs.
- **`PlexLibrary`** — orchestrates both. Stores `_active_token` (user-specific) for browser deep links separately from admin token. Caches user token/title/content-rating-filter. On-deck skipped for managed users (server rejects their tokens). Owns `PlexTimelineReporter` — started/stopped via `processStarted`/`processFinished`. Stores `_current_play_part_id`, `_audio_id_map`, `_sub_id_map` for track persistence. `_mpvLaunchReady` signal carries 6 args: `(url, title, start_ms, duration_ms, part_id, intro_end_ms)`. Public signals: `markersReady(intro_end_ms: int)`, `mpvPositionChanged(int ms)`. Slot: `seekMpv(ms: int)`.
- **Poster cache:** `_poster_executor` (10 workers) separate from `_executor` (2 workers). Cached posters pre-resolved on worker thread before emitting to QML — no placeholder flash on warm load.

### Recently Played Widget

**Files:** `backend/recently_played.py`, `qml/screens/RecentlyPlayedWidget.qml`, `qml/screens/HomeScreen.qml`

- `RecentlyPlayedManager` is passed to all 6 launching backends at startup and exposed as `recentlyPlayed` context property.
- `record(source, title, artwork, nav_params)` — always called on the main thread. De-dups by `(source, nav_params)` dict equality: replaying an item moves it to the front. Max 50 entries. Atomic JSON write via `tempfile.mkstemp` + `os.replace`. Emits `changed` signal after every write.
- `getRecent()` — returns top 5 as `QVariantList` of dicts with keys `source`, `title`, `artwork`, `nav_params`.
- **Thread safety:** `record()` must always be called on the main thread. Plex video is the only async case: `_pending_record_*` fields are populated on the worker thread, then read in `_on_mpv_launch_ready` (main-thread signal handler). All other backends call `record()` from the QML `_playAlbum()` (Plex music, local music) or their `launchGame()`/`launchApp()` slots (retro, Steam, Moonlight).
- **Deep navigation (navTarget):** Pressing A on a widget card calls `HomeScreen.onActivated(source, navParams)`. HomeScreen maps `source` via `slugMap` to the target tab slug, finds the tab index, and calls `Loader.setSource(url, {navTarget: navParams})`. Each tab screen reads `navTarget` in `onActiveFocusChanged` (after all init) and navigates to the item's detail view. Guard: `_navTargetApplied: bool` — only fires once per screen instance (Loader recreates the screen on each tab switch, so the guard resets naturally).
- **navTarget nav_params by source:**

| source | Required nav_params keys | Navigation action |
|---|---|---|
| `"retro"` | `rom_path`, `system_folder`, `system_display_name` | `library.selectSystem(system_folder)` then search gamesModel |
| `"steam"` | `app_id` | search `steam.gamesModel` (synchronous — `steam.refresh()` is sync) |
| `"moonlight"` | `host_address`, `app_name`, `image_path`, `host_name` | construct `_navTargetAppData` directly — no model search |
| `"plexvideo"` | `rating_key`, `media_type` ("movie"/"show") | movie: `plex.fetchMovie(rating_key)` direct (no model search); show: set `selectedShowRatingKey` direct |
| `"plexmusic"` | `rating_key` | `_selectedAlbumKey = rating_key`, `currentView = "album"` |
| `"local"` | `folder_path` | `_selectedAlbumFolder = folder_path`, `currentView = "album"` |
| `"localvideo"` | movie: `path`, `title`, `poster_path`, `year`, `genre`, `description`; show: `show_path`, `show_name`, `show_poster_path`, `show_year`, `show_description` | construct `_selectedMovieData` / `_selectedShowData` directly |

### Local Video Library

**Files:** `backend/local_video_library.py`, `qml/screens/LocalVideosScreen.qml`

#### Cache Layout

```
~/.config/htpcstation/local_videos_cache/
  movies/
    artwork_custom/     # user-placed overrides — any image ext (.jpg/.jpeg/.png/.webp)
    artwork_scraped/    # scraper-written, always .jpg
    library.json        # keyed by filename stem, e.g. "The Matrix (1999)"
  tv_shows/
    artwork_custom/
    artwork_scraped/
    library.json        # keyed by show folder name, e.g. "Breaking Bad"
  {slug}/               # custom categories: slug = _slugify(name)
    artwork_custom/
    library.json        # user-authored only; no artwork_scraped dir
```

`_slugify(name)` → `re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')`.  
Custom categories have no `has_scraped_art` dir (TMDb scraping not supported for custom categories).

#### `library.json` Schema

```json
{
  "The Matrix (1999)": {
    "title":          "The Matrix",
    "year":           1999,
    "description":    "A computer hacker learns from mysterious rebels...",
    "genres":         [],
    "rating":         "",
    "tmdb_id":        603,
    "poster_scraped": "/home/user/.config/htpcstation/local_videos_cache/movies/artwork_scraped/The Matrix (1999).jpg",
    "custom": {
      "title": "The Matrix (Director's Cut)"
    }
  },
  "Unknown Movie": {
    "tmdb_id": null
  }
}
```

- `tmdb_id: null` = tombstone — confirmed TMDb miss, skip on next scrape.
- `custom` dict: user edits — overrides any same-named base field at display time.
- `poster_scraped` path is absolute; `resolve_poster()` checks disk existence before returning it.

#### Poster Resolution Priority

`LocalVideoCache.resolve_poster(key)`:
1. `artwork_custom/{key}.{jpg,jpeg,png,webp}` — first matching extension wins.
2. `poster_scraped` path in `library.json` — only if the file still exists on disk.
3. `""` — no poster available.

#### Custom Override (User Edits)

To override a field for a movie/show, edit `library.json` and add values under the `"custom"` key:

```json
"The Matrix (1999)": {
  ...
  "custom": {
    "title": "The Matrix (Extended)",
    "description": "My custom description."
  }
}
```

`custom` fields are preserved by `set_entry()` — re-running the scraper will never overwrite them.

To use a custom poster image: drop any `.jpg`/`.jpeg`/`.png`/`.webp` file named after the movie stem (e.g. `The Matrix (1999).jpg`) into `artwork_custom/`. It takes priority over the scraped poster automatically.

#### TMDb API Key Setup

1. Register at [themoviedb.org](https://www.themoviedb.org/) and generate a v3 API key.
2. Open **Settings → Videos → TMDb → API Key** and enter the key.
3. The key is stored in `~/.config/htpcstation/config.json` under `"tmdb": {"api_key": "..."}`.
4. Use **Scrape Movies** / **Scrape TV Shows** buttons in Settings → Videos → TMDb to run a scrape.

#### Threading Notes

- `LocalVideoCache` is **main-thread only** — never call it from a worker thread.
- `TmdbScraper` is pure Python (no Qt) — runs on a daemon `threading.Thread` started by `LocalVideoLibrary._start_scrape()`.
- Progress and completion signals are dispatched back to the main thread via `QMetaObject.invokeMethod(..., Qt.ConnectionType.QueuedConnection, ...)` trampoline slots.
- The scrape guard (`_scrape_thread.is_alive()`) automatically resets when the thread finishes.

### MPV Architecture
- `LibMpvPlayer` (`backend/mpv_launcher.py`): in-process MPV via `python-mpv` (libmpv ctypes). Created with `wid=int(window.winId())` so MPV renders into the Qt window — no subprocess, no window hide/show. Auto-detects Wayland vs Xorg via `XDG_SESSION_TYPE`. Wayland → `hwdec=vaapi-copy, gpu_context=wayland`. Xorg → `hwdec=vaapi, gpu_context=x11`. Gamepad bindings registered via `player.keybind()` at startup — no `input.conf` file written to disk. Verified button names on 8BitDo Micro D-input: `GAMEPAD_ACTION_DOWN` (A/east = pause/play), `GAMEPAD_DPAD_*` (seek/volume), `GAMEPAD_LEFT/RIGHT_SHOULDER` (audio/tracks), `GAMEPAD_ACTION_LEFT` (Y = subtitle picker), `GAMEPAD_ACTION_UP` (X = show-progress), `GAMEPAD_START` (quit). L2/R2 use `on_key_press` callbacks with 0.5s debounce — one seek per tap.
- `processStarted` signal fires from `wait_until_playing()` (first frame ready), not from process start. `processFinished` fires from `end_file` event callback. Both are marshalled to the main thread via `QMetaObject.invokeMethod`.
- `MpvSubtitleOverlay.qml`: in-process `FocusScope` overlay (not a separate `Window`) — works correctly since MPV renders in the same Qt window. Triggered by Y button via `subtitlePickerRequested` signal chain (`LibMpvPlayer` → `PlexLibrary` → QML). Calls `plex.getMpvSubtitleTracks()` / `plex.setMpvSubtitleTrack()` / `plex.persistTrackSelection()`.
- `PlexTimelineReporter` (`backend/plex_timeline.py`): daemon thread, POSTs to `/:/timeline` every 10s. Position updated via push-based `@property_observer('time-pos')` callback (registered in `PlexLibrary.set_wid()`). Pause state updated via `@property_observer('pause')`. No polling. Sends `"stopped"` on exit. Session identified by per-play `uuid4()`.
- Stream URLs use transient token (`GET /security/token?type=delegation&scope=all`) — long-lived token never exposed to the player.
- `MpvIpc` (Unix socket IPC client) removed. All position/state reads use libmpv property observers.

### Retro Scraper Architecture

**Files:** `backend/retro_scraper.py`, `backend/scrapers/`, `backend/gamelist.py`, `backend/library.py`

- `RetroScraper(QObject)` is the orchestrator exposed as `retroScraper` context property. `scrapeAll()` / `scrapeSystem(system)` / `cancelScrape()` are QML slots.
- Scraping runs in `_ScrapeThread(QThread)`. Progress, finish, error, and cancel signals are emitted via `QMetaObject.invokeMethod(..., QueuedConnection)` trampolines back to the main thread.
- `scrapeFinished = Signal(int, int, int, 'QVariantMap')` — args: scraped, skipped, failed, source_counts. `source_counts` is a dict mapping source name → number of games it contributed at least one field for. This must be treated as `QVariantMap` so PySide6 marshals it correctly to QML.
- `AbstractScraperSource._quota_exhausted: bool = False` — set when the source returns 429 (or 430 for ScreenScraper). `_scrape_one()` checks this before calling `search()`. Once set, the source is skipped for all remaining games without network calls.
- `_apply_result(game, result, config)` merges scraped data into a `Game` object. Sets `game.image_path` from `result.thumbnail_path` (or `result.screenshot_path` if `config.scraper_preview_image == "screenshot"`), only when `game.image_path` is currently `None` — never overwrites existing miximages.
- **Log:** `~/.config/htpcstation/scraper.log`. Truncated at the start of each `_start_scrape()` call via `handler.stream.seek(0); handler.stream.truncate()` — each session starts fresh.
- **Hasheous endpoint:** `GET https://hasheous.org/api/v1/Lookup/ByHash/md5/{md5}` — the hash is a **path parameter**, not a query parameter. The `/api/v1/Lookup/ByMD5?MD5=...` form returns 404. Response structure: `{"id": int, "name": str, "metadata": [{"source": "IGDB"|"TheGamesDb"|"RetroAchievements", "id": str}]}`.
- **Library scan merge:** `library.py _scan()` always runs `_scan_rom_files()` to discover all ROM files from the filesystem, then builds `gamelist_games = {g.path.resolve(): g for g in parse_gamelist(...)}` and merges. Every filesystem ROM gets an entry; gamelist metadata wins when paths match. ROMs missing from gamelist.xml appear in the library with minimal metadata rather than being silently dropped.
- **Config:** Scraper settings live under `"scraper"` key in `config.json`: `enabled_sources` dict, `credentials` dict (keyed by source name), `overwrite: bool`, `preview_image: "cover"|"screenshot"`.

### Live TV Architecture
- `LiveTvLibrary`: fetches HDHomeRun host from Plex `/livetv/dvrs`, then uses HDHomeRun's own APIs for all guide data. No Plex cloud EPG calls.
- **Data sources:**
  - `GET http://{host}/discover.json` → `DeviceAuth` token (local, instant)
  - `GET http://{host}/lineup.json` → 67 tunable channels with VCN, name, stream URL (local, instant)
  - `GET https://api.hdhomerun.com/api/guide?DeviceAuth={token}` → 58 channels with full guide (cloud, ~2s)
- **Current program detection:** `StartTime <= now < EndTime` — HDHomeRun timestamps are accurate Unix seconds.
- **Cache:** `~/.config/htpcstation/livetv_cache/guide_cache.json` — single file, all channels. Warm start serves cache instantly, background refresh updates in-place.
- **Force refresh:** Y button in guide clears cache and re-fetches.
- **Why not Plex cloud EPG:** The `/{epg_key}/grid` endpoint ignores `channelGridKey` filter — returns the same 607-item cross-channel dataset regardless. Only 19 of 64 channels appeared, only 5 with live data. HDHomeRun guide gives 58 channels, 56 with live data.

### Steam Architecture
- `steam_parser.py`: VDF/ACF recursive descent parser. Discovers games from Flatpak + native paths. Filters non-games (Proton, runtimes, incomplete installs).
- `steam_library.py`: `SteamSourceListModel` (extensible — designed for future GOG/Epic sources) + `SteamGameListModel`. `toggleFavorite(index)` persists to `gamelist.xml`. `getFavorites()` returns `{source: "steam", ...}` — source key required for badge rendering. Steam-only: no Moonlight injection.
- Artwork: custom override → HTPC cache → local Steam cache → CDN download. Always returns local path.

### Moonlight Architecture
- Two-phase refresh: Phase 1 (sync, local config read) → Phase 2 (threaded: TCP probe + app enumeration + artwork + play history).
- `artwork_index.json` tracks `steam_app_id` per app — used for future rich metadata.
- `MoonlightLibrary` owns its own `getRecentlyPlayed()` (reads `moonlight_play_history.py`, returns up to 20 entries sorted by `last_played` desc) and `clearRecentlyPlayed()`. No injection into `SteamLibrary`.
- `MoonlightScreen.qml`: dedicated tab with sources (Recently Played, Favorites, Apps), app grid/list, detail view. View mode persisted via `settings.moonlightViewMode` — `on_ViewModeChanged` overrides child components' `setPcGamesViewMode()` calls.

### Browser Extension Architecture
- No ES modules — files concatenated via manifest `js` array: `generated_mapping.js` → `mappings/*.js` → `content.js`
- `generated_mapping.js` written at deploy time from `controller_mapping.json` via `generate_mapping_js()`, which reads the **SDL half** of each dual-record entry and translates to Web Gamepad API button/axis indices. Falls back to a comment-only stub if no SDL data recorded yet.
- Deployed to `~/.var/app/com.brave.Browser/config/htpcstation-extension/` before each launch
- Flatpak override `--filesystem=/run/udev:ro` applied automatically for gamepad access

### Gamepad / Controller Mapping Architecture

**Dual-record format** (since M8-B, CP32). Every entry in `controller_mapping.json` has:
```json
{
  "evdev": {"type": "button"|"axis", "code": <int>, "value": <int>},
  "sdl":   {"type": "button"|"axis"|"hat", ...} | null,
  "also":  [{"evdev": {...}, "sdl": {...}}]
}
```
- `evdev` half — used by `gamepad.py` (`build_evdev_lookup()`) for Qt key injection and by `LibMpvPlayer` (same path).
- `sdl` half — used by `build_hotkey_cfg()` for `retroarch.cfg` and by `build_web_gamepad_mapping()` for the browser extension.
- `also` array — co-firing events from dual-reporting devices (D-input triggers emit both an axis event and a button event for the same physical press). Both are stored; `seed_from_controller_mapping()` registers all of them in the SDL lookup.
- Old single-record format (pre-M8-B) is migrated transparently by `load_mapping()`: wraps existing record as `evdev` half, sets `sdl` to `null`.

**SDL resolution lifecycle:**
1. `GamepadManager.startRawMode()` → calls `SdlResolver.open(device_name, button_codes, axis_codes)`, then `seed_from_controller_mapping(load_mapping())`.
2. Raw mode active → `rawInput` signal emits `(evtype, code, value)` to QML dialogs.
3. QML captures input → calls `settings.saveControllerMapping(recordedList)` or `settings.setHotkeyModifier/setHotkeyActionByEvdev/ByAxis()` — all call `resolver.resolve()` while resolver is still open.
4. `GamepadManager.stopRawMode()` → calls `SdlResolver.close()`.
5. **Critical ordering:** emit `buttonCaptured`/`axisCaptured` signals (which trigger `settings` slots) **before** calling `stopRawMode()`. `ModifierCaptureDialog` and `ControllerMappingDialog` both follow this order.

**SdlResolver.resolve() priority:**
1. `_evdev_event_to_sdl` — seeded from saved controller mapping via `seed_from_controller_mapping()`. Covers all inputs the user physically pressed during the mapping wizard with correct labels.
2. `_evdev_axis_to_sdl_record` — built from `SDL_GameControllerGetBindForAxis()` heuristic during `open()`. Fallback for inputs not in the mapping (e.g. Home/Guide button).
3. `_evdev_button_to_sdl` — sorted-position fallback for buttons (EV_KEY codes → SDL button indices by sort order).

**D-input trigger detection** (critical gotcha): D-input devices report triggers as SDL joystick **buttons** (not axes). `SdlResolver.open()` detects this: GC API axis binds that map to joystick buttons are identified by finding which joystick axis indices are **not** bound to any GC logical axis. Those unbound joystick axis indices correspond to evdev axis codes that SDL treats as buttons. The resolver stores a `{"type": "button", ...}` record for those evdev axis codes so `build_hotkey_cfg()` writes `input_*_btn` (not `input_*_axis`) for RetroArch.

**Hotkey modifier** is always written as `input_enable_hotkey_btn` — axis/hat modifiers are not supported by RetroArch. `build_hotkey_cfg()` writes `nul` for axis/hat keys of the modifier regardless of the SDL record type.

**Duplicate prevention:** `_store_hotkey_sdl()` evicts any other hotkey action or the modifier that already uses the same SDL record before assigning the new one. Prevents RetroArch receiving the same button for two functions.

**Face button label layout mapping:**
- SDL always uses Xbox button names internally: A=East, B=South, X=West, Y=North.
- Standard layout (Nintendo-style): A=East, B=South, **X=North, Y=West** — SDL X and Y are swapped vs display labels.
- Alternate layout (Xbox-style): A=South, B=East, X=West, Y=North — SDL names match display labels except A↔B swap.
- `_FACE_LABELS_STANDARD` / `_FACE_LABELS_ALTERNATE` maps in `settings_manager.py` translate SDL label → display label + cardinal position (e.g. "A (East)").

**Hold-to-skip in mapping wizard** (`ControllerMappingDialog.qml`): skippable actions (triggers, shoulders) show a 3s hold timer. Button tap → records on release. Button hold 3s → skips. Known issue: dual-reporting inputs (D-input triggers) fire an axis event first (starts timer, sets `_holdSkipCode`), then a button event hits the `else` branch and calls `_recordInput` immediately. Fix needed: ignore button press events when `_holdSkipCode !== -1`.

### Config File Structure

```json
{
  "rom_directory": "/path/to/ROMs",
  "retroarch": {
    "command": "flatpak run org.libretro.RetroArch",
    "cores_directory": "~/.var/app/org.libretro.RetroArch/config/retroarch/cores"
  },
  "systems": { "gb": { "display_name": "Game Boy", "core": "gambatte_libretro.so", "extensions": [".gb"] } },
  "plex": { "token": "...", "server_id": "...", "server_url": "http://192.168.0.2:32400", "user_id": 0, "player": "mpv", "client_id": "<stable-uuid>" },
  "browser": { "command": "flatpak run com.brave.Browser" },
  "moonlight": { "command": "flatpak run com.moonlight_stream.Moonlight", "host_uuid": "..." },
  "ui": { "video_snap_autoplay": true, "video_snap_delay_ms": 1500, "show_network_indicator": true, "button_layout": "standard", "moonlight_view_mode": "grid", "theme_name": "default", "accent_color": "#e94560", "focus_ring_color": "#e94560" },
  "tabs": { "show_retro_games": true, "show_pc_games": true, "show_moonlight": true, "show_watch": true, "show_listen": true },
  "hotkey_modifier_evdev": 316,
  "hotkey_modifier_sdl": {"type": "button", "sdl_button": 5, "label": "Guide"},
  "hotkey_mapping": {
    "save_state": {"type": "button", "sdl_button": 2, "label": "X"},
    "exit_emulator": {"type": "hat", "sdl_hat": 0, "dir": "down"}
  },
  "rewind_enable": false,
  "rewind_buffer_size": 100,
  "rewind_granularity": 8
}
```

---

## Full Gotchas Catalogue

### QML
- **`id: root` shadowing** — Never use in components. `vpx()` is on the ApplicationWindow's `root`.
- **Signal name conflicts** — Never name a signal `<propertyName>Changed`. QML auto-generates those.
- **Property bindings don't re-evaluate for API calls** — Use `optionsProvider` function called on demand, not static bindings.
- **QString to int** — Use `parseInt(value)` in QML before passing to `@Slot(int)`.
- **Image source local paths** — Need `"file://"` prefix. Check `startsWith("http")` before prepending.
- **Context property null on startup** — Guard all bindings: `plex ? plex.model : null`.
- **HomeScreen tab arrays** — Build imperatively in `Component.onCompleted`, never via bindings to `settings.*`. Binding causes cascading focus destruction and app freeze.
- **One `Component.onCompleted` per scope** — QML silently fails with "Property value set multiple times" if you have two.
- **PySide6 custom signals in `Connections`** — May not work. Use reactive property bindings or imperative code instead.
- **Missing `}` in SettingsScreen handler chain** — Silently breaks the entire Settings tab with no console error.
- **Stderr filter hides QML errors** — Disable `_start_stderr_filter()` in `main.py` when debugging QML.
- **Focus scale must target inner content, not delegate root** — Applying `scale` to a `FocusScope` delegate root inside a `clip: true` ListView/GridView clips the scaled item at its original bounds. Apply scale to the inner card `Rectangle` instead. Grid delegates need `z: activeFocus ? 1 : 0` so focused items render above neighbours. Use `Theme.focusScale` and `Theme.focusScaleDuration` tokens.
- **ListView/GridView highlight centering** — All list/grid views use `highlightRangeMode: ApplyRange` with `preferredHighlightBegin: height * 0.35` and `preferredHighlightEnd: height * 0.65`. Use `ApplyRange` (not `StrictlyEnforceRange`) so short lists still allow focus at edges. Add these three properties to any new ListView/GridView.
- **`LibraryHeader.qml` — do not alias `bottom`** — `bottom` is a FINAL property of QML's `Item` (it belongs to the anchors group). Defining `readonly property alias bottom: statusBar.bottom` inside a component raises "Cannot override FINAL property" at startup and freezes the app. Screens anchor content using `header.bottom` directly — reading the built-in property of a sibling is valid; only redefining/aliasing it inside the component is illegal. Also: anchoring to `header.contentBottom` (or any child-of-sibling property) raises "Cannot anchor to an item that isn't a parent or sibling" and produces empty screens. Always anchor content to `header.bottom`.
- **`LoadingOverlay.qml` must import `".."`** — `Theme` is a `pragma Singleton` registered in `qml/qmldir`. Components in `qml/components/` cannot access it unless they explicitly `import ".."`. Without this import, `delay: Theme.loadingOverlayDelay` coerces to `0` on binding failure (fires immediately) and `color: Theme.colorBackground` stays at Qt Quick's Rectangle default (white). Result: a white flash every time `loading` toggles true. Any new component in `qml/components/` that references Theme must include `import ".."`.
- **Do not restore sort/genre from global settings in `Component.onCompleted`** — The backend stores sort per-section key in `_section_sort` (state.json) and genre in `_section_genre`. The settings keys (`sortPlexMovies` etc.) are global and can diverge from the per-section backend state. Instead, add a `property string sectionKey: ""` to the view, bind it to `watchScreen.selectedSectionKey` (or the equivalent), and sync `_currentSort`/`_currentGenreKey` in `onSectionKeyChanged` by calling `plex.getSectionSort(sectionKey)` / `plex.getSectionGenre(sectionKey)`. `_currentGenreTitle` cannot be restored without the genres list — leave it `""` and set it in `onGenresReady` when the matching key is found.
- **`HomeScreen` tab content is loaded on demand** — `Loader.source` starts as `""`. Set it imperatively on A-press; clear it in `returnFocusToTabBar()` to destroy the screen and stop network calls. Do not bind `Loader.source` to any property.
- **navTarget must be applied in `onActiveFocusChanged`, not `Component.onCompleted`** — `Component.onCompleted` fires during component construction before focus is granted. 80ms later, `tabEnterTimer` calls `forceActiveFocus()`, which triggers `onActiveFocusChanged` and runs initialization code (`_routeFocus()`, `selectLibrary()`, `steam.refresh()`, etc.) that resets `currentView` back to the default list. Any navTarget navigation set in `Component.onCompleted` is silently overwritten. Always place the navTarget block at the very end of the `if (activeFocus)` block in `onActiveFocusChanged`, after all existing init. Use `property bool _navTargetApplied: false` as a one-shot guard — `onActiveFocusChanged` may fire again if the user returns to the screen.
- **navTarget model searches fail on cold start when the model loads async** — For screens where the model is populated by an async operation (Plex network load, Moonlight refresh), the model will be empty when `onActiveFocusChanged` fires on the first tab visit after app restart. Do not search an async model in the navTarget block. Instead: (a) call any synchronous slot that populates the model before searching (e.g. `library.selectSystem()` for retro games which is a synchronous local scan), or (b) skip the model search entirely and navigate directly by setting the required properties from navTarget fields (e.g. `plex.fetchMovie(navTarget.rating_key)` without needing `selectedMovieIndex`). The pattern of directly constructing a data object from navTarget fields (as in `LocalVideosScreen._selectedMovieData` and `MoonlightScreen._navTargetAppData`) avoids model dependency entirely and is the most robust approach.

### Plex
- **Managed user tokens get 401 from server** — Always use admin token for server API calls. User token only for browser deep links.
- **No on-deck for managed users** — Server rejects managed user tokens on on-deck endpoint. Hide Continue Watching for managed users.
- **Content rating filter must be cached** — Store alongside user token; restore on `_on_setup_ready()` (main-thread handler for `_setupReady` signal).
- **User token caching** — Only call `switch_user()` when user ID changes. Cache `_cached_user_token/title/content_rating_filter`.
- **`selectServer`/`selectUser` must not block** — Save config and invalidate client only. Lazy reconnect on next `refresh()`.
- **Old plex.tv API endpoints** — `/api/home/users` requires token as query param, returns XML.
- **Plex Web user selection** — Cannot be bypassed via URL. Extension auto-clicks matching user tile.
- **Deep link lost after user selection** — Extension saves URL, waits 1.5s, re-navigates.
- **Auto-play requires `hashchange` listener** — Content script runs once; re-navigation is a hash change.
- **`--autoplay-policy=no-user-gesture-required`** — Required for `video.play()` from content scripts.
- **Plex class name hashes change between versions** — Always use `[class*="prefix"]`, never exact class names.
- **Escape must be dispatched on overlay element** — Not on `document`.
- **Bare `.click()` doesn't work on React buttons** — Need full pointer event sequence: `pointerdown` → `mousedown` → `pointerup` → `mouseup` → `click`.
- **React re-renders swap DOM elements** — Save focus coordinates before click; use `elementFromPoint()` to find replacement.
- **Focus stack pollution** — Only push on layer-opening clicks (`aria-haspopup` or known trigger `data-testid`).
- **Virtual scrollers break index-based navigation** — Use position-based navigation (Y coordinate comparison).
- **Mini player `<video>` triggers `isPlayerActive()`** — Check for `AudioVideoFullPlayer` (full-screen only).

### Brave / Browser
- **Flatpak `--user-data-dir` outside sandbox ignored** — Use path inside sandbox: `~/.var/app/com.brave.Browser/config/htpcstation-browser/`.
- **Existing Brave instance ignores flags** — Dedicated `--user-data-dir` creates separate process.
- **Session accumulation** — Clear `Sessions/` and `Session Storage/` before each launch.
- **`window.close()` blocked in kiosk mode** — Use `flatpak kill <app_id>`.
- **Flatpak browsers can't see gamepads** — Apply `flatpak override --user <app_id> --filesystem=/run/udev:ro`.

### Steam
- **Don't hide window on Steam launch** — `xdg-open` exits immediately; can't track game exit. WM handles focus return automatically.
- **`getFavorites()` must include `source: "steam"`** — Badge renderer treats anything not `"steam"` as Moonlight.

### Moonlight
- **QSettings INI fields are all lowercase** — `hostname`, `localaddress`, `uuid`, not camelCase.
- **`customname=false` means no custom name** — Not the string "false".
- **CLI spawns Qt GUI** — Stderr has SDL/Qt noise; ignore entirely.
- **Steam search accuracy** — Non-game apps may match wrong results. Users can drop custom artwork in `artwork_custom/`.

### MPV
- **Wayland needs `vaapi-copy`** — `vaapi` direct display path doesn't work without a copy step on Wayland EGL.
- **Fedora codec-restricted packages** — `ffmpeg-free` causes `libopenh264` to win H.264 decoder selection over VA-API. Swap for `ffmpeg` from RPM Fusion. `libva-intel-media-driver` → `libva-intel-driver` (RPM Fusion).
- **AV1 requires Gen 12+ hardware** — Kaby Lake (UHD 620) has no AV1 hardware decode.
- **`mpv-libs` required** — `python-mpv` loads `libmpv.so` at runtime. On Fedora: `sudo dnf install mpv-libs`. On Debian/Ubuntu: `sudo apt-get install libmpv2`. The `mpv` binary alone is not sufficient.
- **`LibMpvPlayer.set_wid()` must be called after `window.showFullScreen()`** — `winId()` is only valid after the window is mapped. Call `plex_library.set_wid(int(window.winId()))` in `main.py` after `showFullScreen()`.
- **Gamepad button names are SDL positional, not label-based** — The 8BitDo Micro uses `hint:!SDL_GAMECONTROLLER_USE_BUTTON_LABELS` in its SDL mapping. Verified with `mpv --input-test`: A (east, evdev 304) = `GAMEPAD_ACTION_DOWN`, B (south, evdev 305) = `GAMEPAD_ACTION_RIGHT`. Always verify with `mpv --input-gamepad=yes --input-test --force-window --idle --input-conf=/dev/null` on the actual device.
- **`SDL_GAMECONTROLLERCONFIG` override is ignored** — The 8BitDo Micro's mapping is already in the system SDL database and cannot be overridden via env var on this device.
- **L2/R2 debounce uses `on_key_press` callback with 0.5s window** — The analog axis fires continuously while held. The debounce closure uses a `[float]` list to capture mutable state across calls. Do not use `{no-repeat}` in keybinds — it has no effect on axis-held state.
- **`_mpvLaunchReady` carries 6 args** — `(url, title, start_ms, duration_ms, part_id, intro_end_ms)`. All test mocks must match this signature.
- **`processStarted` fires from `wait_until_playing()`, not from process start** — The signal is emitted when the first frame is ready. `processFinished` fires from the `end_file` event callback. Both are marshalled to the main thread via `QMetaObject.invokeMethod`.
- **python-mpv callbacks run on the mpv event thread** — Never call Qt UI methods directly from a property observer or event callback. Always use `QMetaObject.invokeMethod` with `QueuedConnection`.

### Plex Cache
- **`_PLEX_CACHE_DIR` and `_POSTER_CACHE_DIR` are module-level constants** — Computed at import time from `CONFIG_DIR`. Patching `CONFIG_DIR` after import has no effect on them. Always patch the constants directly: `patch("backend.plex_library._PLEX_CACHE_DIR", ...)`.
- **Startup cache load is async** — `_worker_load_all_caches` runs on `_cache_executor` (dedicated single-thread pool). It emits `_librariesReady` and `_onDeckCacheReady` which are delivered via `QueuedConnection` (queued to main thread). WatchScreen's `Connections` block handles `onLibrariesModelChanged` — do not call `_getVideoLibraries()` before this fires or you get only the hardcoded Live TV entry.
- **All worker signal connections must use `QueuedConnection`** — PySide6 `AutoConnection` from a Python `ThreadPoolExecutor` thread behaves as `DirectConnection` (not `QueuedConnection`), because executor threads are not `QThread` subclasses. The slot runs on the worker thread, and QML observers never fire. All 11 worker signals in `PlexLibrary.__init__` are connected with explicit `Qt.ConnectionType.QueuedConnection`.
- **`sectionLoadFailed` signal** — Emitted by `_worker_load_section` when the network call fails after cache has already been emitted. QML uses this to clear `_loading` flags so cached data is visible (not covered by the loading spinner). WatchScreen shows a "Network unavailable" toast on this signal.
- **`plexError` cross-thread delivery** — `_on_plex_error` runs on the worker thread (via `set_error_callback`). It uses `QMetaObject.invokeMethod` with `QueuedConnection` via a `_emit_plex_error` trampoline slot to ensure delivery on the main thread.
- **Server URL cached in `config.json`** — `_worker_setup()` persists the resolved server URL to `config.plex_server_url` on success and falls back to it when plex.tv is unreachable. The local server is often reachable even without internet.
- **Cache-first `selectLibrary()`** — Always loads movies/shows/artists from disk cache synchronously (main thread) before submitting the network backfill to the executor. Poster paths pre-resolved via `_resolve_cached_posters()`. When `_client is None`, emits `sectionLoadFailed` for the offline toast and returns.
- **Incremental cache saves** — `_save_movies_cache`/`_save_shows_cache`/`_save_artists_cache` replaced with merge-by-`rating_key` pattern: `_*_to_dict()` snapshots on main thread, `_merge_and_write_*_cache()` does read-merge-write on `_cache_executor`. Called on every page, not just page 1. Existing entries preserved — a full cache is never overwritten by a partial load.
- **Empty network response guard** — `get_library_items()` returns `([], 0)` on soft failure (retry exhaustion, no exception). All worker functions (`_worker_load_section`, `_worker_load_more_movies`, `_worker_load_more_shows`) check for this and emit `sectionLoadFailed` instead of overwriting the cached model with nothing.
- **Server URL probe on startup** — `_worker_setup()` probes the primary URL with `GET /identity` (3s timeout) before creating `PlexClient`. If unreachable (e.g. local IP on external network), iterates through `_all_server_urls` to find a working remote/relay URL. Config always caches the highest-priority (local) URL, not the session URL. If all probes fail, client is still created with the best URL (existing retry/fallback is the safety net).
- **`_setup_client()` runs on a worker thread** — `refresh()` submits `_worker_setup` to `_executor`. All blocking network I/O (plex.tv resource discovery, URL probing, user switching) runs off the main thread. Results are marshalled back via `_setupReady` signal + `_on_setup_ready` slot (QueuedConnection). Shared state (`_client`, `_server_url`, `_account`, `_active_token`) is only written in `_on_setup_ready` on the main thread.
- **`fetchArtistPreview` replaces `getArtist`** — `PlexArtistList._updatePreview()` uses async `fetchArtistPreview()` + `artistPreviewReady` signal. The sync `getArtist()` method has been removed. The `ratingKey === _lastPreviewKey` guard in QML discards stale results from fast scrolling.
- **`selectLibrary()` skips cache reload when model has content** — Calling `set_movies()`/`set_shows()`/`set_artists()` triggers `beginResetModel()`/`endResetModel()` which resets the GridView's `contentY` to 0. When returning from a detail view, `onCurrentViewChanged` calls `selectLibrary()` again (lazy refresh). If the model already has content, skip the cache reload to preserve scroll position. The network backfill still runs and will update the model if the data changed.
- **`_on_movies_ready`/`_on_shows_ready`/`_on_artists_ready` skip replacement when model is larger** — The network backfill returns page 1 (50 items). If the model already has 500 items from cache, replacing it with 50 items causes the user's scroll position to jump (item #75 no longer exists). Guard: `if len(movies) >= len(self._movies_model._movies)`.
- **Never call `poster_cache.get_poster()` in loops on worker threads** — Each `get_poster()` downloads a poster synchronously (1–5s on remote connections). For 10 albums, that's 10–50s blocking the worker. Instead: pre-resolve from disk cache (`_cache_path().exists()`), emit immediately, then submit uncached downloads to `_poster_executor` (parallel, 10 workers). Use the `posterUpdated(ratingKey, url)` signal for QML updates — never re-emit the full data structure, which resets ListView focus/scroll.
- **`posterUpdated` signal for in-place QML poster updates** — Fetch workers emit `posterUpdated(ratingKey, posterUrl)` after each parallel poster download completes. QML handles this by finding the item in the JS array by ratingKey, creating a new array via `slice()` with the updated item, and restoring `currentIndex` + `activeFocus` around the swap. Never re-emit `artistDetailReady`/`recentAlbumsReady` for poster updates — that replaces the entire model and resets focus.
- **`fetchGenres()` replaces `getMovieGenres`/`getShowGenres`** — Genre fetching is now async via `fetchGenres()` + `genresReady(sectionKey, genreList)` signal. Results cached per section key in `_genres_cache` — subsequent calls emit from cache without a network call. QML sort/filter overlays call `plex.fetchGenres()` on open and populate `_genres` in `onGenresReady`.
- **`_probe_server_url` makes real HTTP calls in tests** — `conftest.py` has an autouse fixture that patches `backend.plex_library.requests` to prevent 3s probe timeouts. Tests that specifically test probe behavior patch `requests.get` themselves.
- **Sort/genre state is per section key** — `_section_sort: dict[str, str]` and `_section_genre: dict[str, str]` keyed by Plex section key (e.g. `"4"`). Persisted to `plex_cache/state.json` on every sort/filter change. Loaded at startup in `_worker_load_all_caches`. Do not use a single shared `_current_sort` field. QML views query the authoritative backend state via `plex.getSectionSort(sectionKey)` / `plex.getSectionGenre(sectionKey)` in `onSectionKeyChanged`. `_SORT_MAP_REVERSE` (class attribute on `PlexLibrary`) provides the API-string → QML-key reverse lookup needed by `getSectionSort`.
- **`selectLibrary()` passes current sort** — Lazy fetch on section entry uses `_section_sort.get(section_key, "")` so the user's sort is preserved across navigation.
- **Poster downloads use `/photo/:/transcode`** — `get_poster_url()` routes through Plex's server-side resize endpoint at 400px wide. `get_authenticated_url()` is for non-poster paths (track streams, etc.) and returns a plain authenticated URL.
- **`_save_sort_state()` is called on the main thread** — It does a read-modify-write on `state.json`. Fast local disk write; acceptable on main thread.

### Plex API
- **Plex cloud EPG `channelGridKey` filter is broken** — The `/{epg_key}/grid` endpoint ignores `channelGridKey` and returns the same full dataset regardless. Use HDHomeRun guide API instead.
- **Plex EPG timestamps may be ~1 year ahead** — The cloud EPG provider returns `beginsAt`/`endsAt` in seconds but offset by ~1 year from wall clock. Do not use for current-program detection. Use HDHomeRun timestamps.
- **`hubs/discover` endpoint takes 26 seconds** — The `/{epg_key}/hubs/discover` endpoint times out with the 10s `_TIMEOUT`. Do not use.
- **Timeline reports use `timeout=5`** — Not `_TIMEOUT=10`. Timeline is fire-and-forget; never raise.
- **Markers are at top level of metadata item** — `metadata.get("Marker", [])`, not inside `Media.Part.Stream`. Type field is `"intro"` or `"credits"`.
- **Transient token replaces long-lived token in stream URL** — `get_transient_token()` returns `""` on failure; fall back to main token silently.

### Gamepad
- **evdev crash loop** — `OSError` catch must wrap the entire `for event in events:` loop, not just `.read()`.
- **Gamepad disconnect segfault** — `_cleanup()` must disconnect the `QSocketNotifier` signal (`activated.disconnect`) and call `deleteLater()` on both the notifier and the handler before removing from the dict. Python GC drops the handler reference before Qt's C++ object tree is cleaned up — if the notifier has a pending activation queued, it fires into a deleted object. `_remove_device()` must call `handler.deleteLater()`, not just `pop()`.
- **Hint label flash on gamepad connect** — `QSocketNotifier` fires immediately on creation if the device fd has buffered kernel events. Use a `_ready` flag (set to `True` after the first `_on_readable` call) to suppress `setGamepadInput()` until the user has actually pressed a button.
- **Auto-repeat timers leak into raw mode** — `startRawMode()` must call `_release_all_keys()`.
- **Mapping dialog can't use Accept/Cancel** — Auto-save on completion; no confirmation button.
- **D-input D-pad as ABS_X/ABS_Y** — Normalize 0-255 range to -1/0/1 using axis range.
- **D-input triggers are SDL buttons, not SDL axes** — `SdlResolver.open()` detects this via the GameController API: any GC logical axis whose bind type is `BINDTYPE_BUTTON` is a trigger mapped as a joystick button. The resolver stores a button SDL record for those evdev axis codes. `build_hotkey_cfg()` must write `_btn`, not `_axis`. If you see `nul` for a trigger hotkey in retroarch.cfg, the trigger was not detected as a button during resolver open.
- **SDL library probing order matters** — `libSDL2-2.0.so.0` is probed first. On Fedora 43 this is `sdl2-compat` (SDL2 shim over SDL3) — function signatures are identical to real SDL2. Do not probe SDL3 before SDL2 or you may get a different GameControllerDB version than RetroArch uses.
- **`seed_from_controller_mapping()` must be called after `open()`** — It builds the primary lookup from the saved mapping (source of truth for all inputs the user actually pressed). The GC API heuristics in `open()` are fallback only. If called before `open()`, `_evdev_hat_to_sdl` is empty and hat axis entries in the mapping will not be skipped correctly.
- **`resolve()` returns `None` when joystick is not open** — Always call `open()` before calling `resolve()`. The `ModifierCaptureDialog` and `ControllerMappingDialog` both emit signals before calling `stopRawMode()` specifically to ensure the resolver is still open when `settings` slots call `resolve()`.
- **Emit capture signals before `stopRawMode()`** — `stopRawMode()` calls `SdlResolver.close()`, which clears all lookup tables. Any `settings.setHotkeyActionByEvdev/ByAxis()` call that needs to resolve an SDL record must happen before `stopRawMode()`.
- **Hold-to-skip dual-reporting bug** — In `ControllerMappingDialog`, dual-reporting inputs (D-input triggers) fire an axis event followed by a button event for the same physical press. The axis event starts the hold timer (`_holdSkipCode = axisCode`). The button event (different code) then hits the `else` branch and calls `_recordInput` immediately. Fix: ignore button press events when `_holdSkipCode !== -1`.
- **`rawInput` emits value=0 for releases** — Raw mode was extended in M6-V2 to emit both press (`value=1`) and release (`value=0`) events for buttons so `ModifierCaptureDialog` can detect tap-vs-hold. The `_handle_button` guard is `if value in (0, 1)` — auto-repeat (`value=2`) is explicitly excluded.
- **All external app launchers must call `setExternalAppActive()`** —
  `GamepadManager` suppresses Qt key injection and clears all held-key
  state when an external app is active. Any launcher that hides the Qt
  window (emulators, browser kiosk, Moonlight, MPV) must call
  `setExternalAppActive(True)` on start and `setExternalAppActive(False)`
  on finish. Omitting this leaves auto-repeat timers running into the
  restored UI — manifests as a grid/list that scrolls to the bottom and
  ignores Up input until the gamepad is disconnected.

### Other
- **Bundled emoji font** — Qt doesn't reliably use NotoEmoji as fallback. Use text equivalents (❤️→♥, 🎵→♫).
- **Unicode Dingbats block causes font fallback stutter** — Characters in the Dingbats block (U+2700–U+27BF, e.g. U+275A `❚`) are not present in the `"Sans"` system font. Qt scans all installed fonts for a fallback glyph at startup and on every render until cached — causes slow load and layout stutter. Use Geometric Shapes (U+25A0–U+25FF: `■`, `▶`, `▲`) or Block Elements (U+2580–U+259F) which are in every standard Linux system font.
- **VAAPI decoding errors in video snaps** — Set `LIBVA_MESSAGING_LEVEL=0` in `main.py`.
- **Qt 6 Video type** — Use explicit `MediaPlayer` + `VideoOutput` with 100ms+ delay before `play()`.
- **`git filter-repo` can be too aggressive** — Review replacement patterns before running.

---

## Temporary Decisions

| Decision | Location | Future Fix |
|---|---|---|
| Plex token in plaintext config.json | `config.json` | Encrypt or use OS keyring |
| Synchronous `getMovie()`/`getShow()` | `plex_library.py` | Move to threaded worker |
| Synchronous `testPlexConnection()` | `settings_manager.py` | Defer to thread |
| Auto-user-select 1.5s fixed delay | `extension/mappings/plex.js` | Detect navigation completion |
| Moonlight artwork: Steam search only | `moonlight_artwork.py` | Add IGDB/RAWG fallback |
| Moonlight detail view lacks metadata | `MoonlightAppDetail.qml` | Wire up gamelist.xml + Steam API via cached steam_app_id |

---

## Gamepad Controls

Default mapping (standard layout, A=East):

| Physical Button | evdev Code | Qt Key | Action |
|---|---|---|---|
| Face East (Accept) | BTN_EAST (305) | Key_Return | Accept / launch |
| Face South (Cancel) | BTN_SOUTH (304) | Key_Escape | Cancel / back |
| Face North | BTN_NORTH (307) | Key_1 | Context 1 (favorite/My List) |
| Face West | BTN_WEST (308) | Key_2 | Context 2 (sort/subtitle) |
| Start | BTN_START (315) | Key_F10 | Quit dialog |
| Select | BTN_SELECT (314) | Key_F9 | Secondary menu |
| Left Shoulder | BTN_TL (310) | Key_PageUp | Quick scroll |
| Right Shoulder | BTN_TR (311) | Key_PageDown | Quick scroll |
| Left Trigger | ABS_Z (2) | Key_Home | Page scroll up |
| Right Trigger | ABS_RZ (5) | Key_End | Page scroll down |
| D-pad | ABS_HAT0X/Y | Key_Up/Down/Left/Right | Navigate |
| Start + Select | — | — | Close browser |

Button Layout setting swaps both display labels AND functional mapping.

---

## History

Checkpoint history and task brief archive: `docs/changelog.md`
