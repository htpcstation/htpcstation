# Task 001 — Fix context1/context2 gamepad key codes

## Context

`controller_mapping.py` defines the `ACTIONS` table which maps semantic action
names to Qt key codes. The gamepad injects these key codes as synthetic
`QKeyEvent`s. `keys.py` `isContext1()` / `isContext2()` check for `Key_1` and
`Key_2` respectively. The `ACTIONS` table currently declares `Key_F1` and
`Key_F2` for context1/context2 — a mismatch that means the gamepad X and Y
buttons never satisfy `keys.isContext1()` / `keys.isContext2()` in QML.

Keyboard shortcuts work because users press the literal `1` / `2` keys
(`Key_1` / `Key_2`), which do match. The gamepad path is broken.

## Objective

Change the two wrong key codes in `ACTIONS` so the gamepad injects the same
keys that `keys.py` checks.

## Scope

**One file, two lines:** `backend/controller_mapping.py`, the `ACTIONS` list.

```python
# Before
("context1", "Face Button North", Qt.Key.Key_F1, False),
("context2", "Face Button West",  Qt.Key.Key_F2, False),

# After
("context1", "Face Button North", Qt.Key.Key_1, False),
("context2", "Face Button West",  Qt.Key.Key_2, False),
```

No other files need changing. `keys.py` and all QML are correct as-is.

## Non-goals / Later

- Do not touch `keys.py`, any QML file, or any other backend file.
- Do not change `DEFAULT_MAPPING` evdev codes — only the Qt key in `ACTIONS`.

## Constraints / Caveats

- `_ACTION_KEY_MAP` is derived from `ACTIONS` at module load, so fixing
  `ACTIONS` automatically fixes the lookup used by `build_evdev_lookup()`.
- Run the full test suite after the change: `python3 -m pytest tests/ -q`.
  All 2,017+ tests must pass. If any test hard-codes `Key_F1`/`Key_F2` for
  context1/context2, update those assertions to `Key_1`/`Key_2`.
