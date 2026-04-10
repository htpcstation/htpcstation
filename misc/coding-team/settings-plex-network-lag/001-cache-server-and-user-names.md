# Task 001 — Cache Plex server name and user title in config

## Context

`SettingsScreen.qml` calls `_getValue("plexServer")` and `_getValue("plexUser")` from delegate property bindings. These call `plex.getServerList()` and `plex.getHomeUsers()` — synchronous HTTP requests to plex.tv on the main thread — just to resolve a display name for the currently selected server/user. Every delegate creation (entering settings, scrolling) triggers fresh network round-trips, causing visible lag.

The `optionsProvider` (dropdown open on A press) also calls these APIs, but that's fine — it fires on user interaction and needs fresh data.

## Objective

Store `server_name` and `user_title` in config.json alongside the existing `server_id`/`user_id`. Use these cached names in `_getValue` instead of making network calls.

## Scope

### 1. `backend/config.py`

- Add `_plex_server_name: str = ""` and `_plex_user_title: str = ""` fields (init in `__init__`, around line 378).
- Add properties: `plex_server_name` / `plex_user_title`.
- Add setters: `set_plex_server_name(name)` / `set_plex_user_title(title)`. These should NOT call `self.save()` — they'll always be set alongside server_id/user_id which already saves.
- Persist in `_build_dict`: add `"server_name"` and `"user_title"` to the `plex` section (around line 937).
- Load in `_load_from_file`: read `"server_name"` and `"user_title"` from the `plex` dict (around line 1096).

### 2. `backend/settings_manager.py`

- Add `plexServerNameChanged` and `plexUserTitleChanged` signals.
- Add `plexServerName` and `plexUserTitle` read-only properties (Property with fget + notify).
- Update `setPlexServerId(server_id: str)` → `setPlexServerId(server_id: str, server_name: str)` — `@Slot(str, str)`. Store both. Emit both changed signals.
- Update `setPlexUserId(user_id: int)` → `setPlexUserId(user_id: int, user_title: str)` — `@Slot(int, str)`. Store both. Emit both changed signals.

### 3. `qml/components/SettingSelect.qml`

- Change signal from `signal selected(var id)` to `signal selected(var id, string label)`.
- Update the emit site (line ~93): `selectRoot.selected(opts[nextIdx].id, opts[nextIdx].label)`.

### 4. `qml/screens/SettingsScreen.qml`

- `_getValue`: replace the `plexServer` branch (lines 111-117) with: `return settings.plexServerName || "Not selected"`. Replace the `plexUser` branch (lines 119-125) with: `return settings.plexUserTitle || "Not selected"`.
- `_setValue`: update the `plexServer` branch to call `settings.setPlexServerId(value, label)`. Update the `plexUser` branch to call `settings.setPlexUserId(parseInt(value), label)`.
- `onSelected` handler (line 550): pass both args: `(id, label) => { settingsScreen._setValue(rowData.settingKey, id, label) }`.
- `_setValue` signature: add `label` parameter. Only `plexServer` and `plexUser` use it; all other callers can pass `""` or `undefined`.

### 5. All other `onSelected` call sites

Grep for `onSelected:` across all QML — any other SettingSelect user needs to accept the new `(id, label)` signature. The second arg can be ignored.

## Non-goals

- Do NOT change `optionsProvider` — dropdown still fetches live from plex.tv.
- Do NOT cache `getServerList`/`getHomeUsers` results in memory.
- Do NOT change `PlexLibrary.getServerList()` or `PlexLibrary.getHomeUsers()`.

## Constraints

- `set_plex_server_name` / `set_plex_user_title` must NOT call `config.save()` independently. The corresponding `set_plex_server_id` / `set_plex_user_id` already call save, and both pairs are always set together. Calling save twice writes the file twice.
  - Actually, the simplest approach: have `set_plex_server_id` accept name as second arg and set both fields before calling save once. Same for `set_plex_user_id`. Then you don't need separate `set_plex_server_name`/`set_plex_user_title` setters at all.
- All existing tests must pass.
