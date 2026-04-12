"""Test that Config.save() snapshots CONFIG_FILE at call time, not at executor-run time.

If the fix is absent, the executor closure captures CONFIG_FILE by name and resolves
it when the thread runs — which may be after the test's patch context has exited,
causing writes to the real ~/.config/htpcstation/config.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.config as config_module
from backend.config import Config, _write_executor


def _make_config(tmp_path: Path) -> Config:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")
    with patch("backend.config.CONFIG_FILE", config_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        cfg = Config()
    return cfg


def test_save_writes_to_patched_path_not_real_path(tmp_path: Path) -> None:
    """Executor must write to the tmp path captured at save() call time."""
    patched_file = tmp_path / "config.json"
    patched_file.write_text(json.dumps({}), encoding="utf-8")

    real_config_path = Path.home() / ".config" / "htpcstation" / "config.json"
    real_existed_before = real_config_path.exists()
    real_mtime_before = real_config_path.stat().st_mtime if real_existed_before else None

    cfg = _make_config(tmp_path)

    # Call save() while the patch is active so _config_file is snapshotted correctly.
    with patch("backend.config.CONFIG_FILE", patched_file), \
         patch("backend.config.CONFIG_DIR", tmp_path):
        cfg.save()
    # Patch has now exited. If the fix is absent, the executor will resolve
    # CONFIG_FILE to the real path when it eventually runs.

    # Drain the executor — wait for the submitted future to complete.
    futures = []
    # We can't easily grab the future returned by submit without modifying prod code,
    # so we submit a sentinel to the same single-worker executor and wait for it.
    sentinel_done: list[bool] = []
    fut = _write_executor.submit(lambda: sentinel_done.append(True))
    fut.result(timeout=5)

    # The patched tmp file should have been written.
    assert patched_file.exists(), "save() did not write to the patched CONFIG_FILE"
    written = json.loads(patched_file.read_text(encoding="utf-8"))
    assert isinstance(written, dict), "Written file is not a JSON object"

    # The real config must NOT have been touched.
    if real_existed_before:
        real_mtime_after = real_config_path.stat().st_mtime
        assert real_mtime_after == real_mtime_before, (
            "Config.save() modified the real config file — race condition fix is broken"
        )
    else:
        assert not real_config_path.exists(), (
            "Config.save() created the real config file — race condition fix is broken"
        )
