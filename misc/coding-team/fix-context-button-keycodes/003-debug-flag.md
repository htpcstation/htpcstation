# Task 003 — Add --debug flag; set ERROR default logging level

## Context

`htpcstation.sh` already passes `"$@"` through to `main.py`. `main()` calls
`logging.basicConfig(level=logging.INFO, ...)`. There is no argument parsing.
All backend modules use `logging.getLogger(__name__)` so a single
`basicConfig` call controls everything.

## Objective

- Default (no flag): log level `ERROR` — only genuine errors visible.
- `--debug` flag: log level `DEBUG` — full operational + trace output.
- `--debug` must be stripped from `sys.argv` before `QGuiApplication(sys.argv)`
  sees it, otherwise Qt will emit an "unknown option" warning.

## Scope

**One file: `main.py`**

Replace the `logging.basicConfig` call at the top of `main()` with argument
parsing + level selection:

```python
def main() -> None:
    import argparse
    import logging

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--debug", action="store_true")
    args, remaining = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining   # strip --debug before Qt sees it

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.ERROR,
        format="%(levelname)s %(name)s: %(message)s",
    )
```

`add_help=False` keeps `--help` available to Qt/QML if needed.
`parse_known_args()` is used so any other Qt flags (e.g. `-platform`) pass
through untouched.

No changes to `htpcstation.sh` are needed — it already forwards `"$@"`.

## Non-goals / Later

- Do not add any other flags.
- Do not change `htpcstation.sh`.
- Do not touch any backend module.

## Constraints / Caveats

- `sys.argv` must be mutated (not just a local variable) before
  `QGuiApplication(sys.argv)` is called on the next line.
- Run `python3 -m pytest tests/ -q` after the change; all tests must pass.
