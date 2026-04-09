# Task 001 — Delete theme image assets

## Context
The user wants to remove the current theme images but keep all Python/QML/test wiring intact for future re-addition.

## Objective
Delete the entire `themes/` directory (both `default/` and `default.bak/` and all contents).

## Scope
- `rm -rf htpcstation/themes/`

## Non-goals
- Do NOT touch any Python, QML, or test files.
- Do NOT remove or modify any theme-related code in `config.py`, `settings_manager.py`, `HomeScreen.qml`, or `test_theme_config.py`.

## Acceptance criteria
- `htpcstation/themes/` directory no longer exists.
- All Python/QML/test files are unchanged.
