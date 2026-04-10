"""Tests for backend/hw_detect.py — VA-API codec detection."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from backend.hw_detect import detect_vaapi_codecs

# Sample vainfo output (trimmed to relevant lines)
_VAINFO_OUTPUT = """\
vainfo: VA-API version: 1.18 (libva 2.18.0)
vainfo: Driver version: Intel iHD driver for Intel(R) Gen Graphics - 23.1.2
vainfo: Supported profile and target pairs for decode:
      VAProfileH264ConstrainedBaseline: VAEntrypointVLD
      VAProfileH264Main               : VAEntrypointVLD
      VAProfileH264High               : VAEntrypointVLD
      VAProfileHEVCMain               : VAEntrypointVLD
      VAProfileHEVCMain10             : VAEntrypointVLD
      VAProfileVP9Profile0            : VAEntrypointVLD
      VAProfileVP9Profile2            : VAEntrypointVLD
      VAProfileH264Main               : VAEntrypointEncSlice
      VAProfileHEVCMain               : VAEntrypointEncSlice
      VAProfileNone                   : VAEntrypointVideoProc
"""


class TestDetectVaapiCodecs:
    def test_parses_vainfo_output(self):
        result = subprocess.CompletedProcess(
            args=["vainfo"], returncode=0, stdout=_VAINFO_OUTPUT, stderr=""
        )
        with patch("backend.hw_detect.subprocess.run", return_value=result):
            codecs = detect_vaapi_codecs()
        assert codecs == ["h264", "hevc", "vp9"]

    def test_deduplicates_profiles(self):
        """Multiple H264 profiles should produce a single 'h264' entry."""
        result = subprocess.CompletedProcess(
            args=["vainfo"], returncode=0, stdout=_VAINFO_OUTPUT, stderr=""
        )
        with patch("backend.hw_detect.subprocess.run", return_value=result):
            codecs = detect_vaapi_codecs()
        assert codecs.count("h264") == 1

    def test_vainfo_not_found(self):
        with patch(
            "backend.hw_detect.subprocess.run", side_effect=FileNotFoundError
        ):
            assert detect_vaapi_codecs() == []

    def test_vainfo_timeout(self):
        with patch(
            "backend.hw_detect.subprocess.run",
            side_effect=subprocess.TimeoutExpired("vainfo", 10),
        ):
            assert detect_vaapi_codecs() == []

    def test_vainfo_nonzero_exit(self):
        result = subprocess.CompletedProcess(
            args=["vainfo"], returncode=1, stdout="", stderr="error"
        )
        with patch("backend.hw_detect.subprocess.run", return_value=result):
            assert detect_vaapi_codecs() == []

    def test_empty_output(self):
        result = subprocess.CompletedProcess(
            args=["vainfo"], returncode=0, stdout="", stderr=""
        )
        with patch("backend.hw_detect.subprocess.run", return_value=result):
            assert detect_vaapi_codecs() == []

    def test_all_known_codecs(self):
        lines = [
            "      VAProfileH264Main    : VAEntrypointVLD",
            "      VAProfileHEVCMain    : VAEntrypointVLD",
            "      VAProfileAV1Profile0 : VAEntrypointVLD",
            "      VAProfileVP9Profile0 : VAEntrypointVLD",
            "      VAProfileVP8Version0 : VAEntrypointVLD",
            "      VAProfileMPEG2Simple : VAEntrypointVLD",
            "      VAProfileVC1Main     : VAEntrypointVLD",
        ]
        result = subprocess.CompletedProcess(
            args=["vainfo"], returncode=0, stdout="\n".join(lines), stderr=""
        )
        with patch("backend.hw_detect.subprocess.run", return_value=result):
            codecs = detect_vaapi_codecs()
        assert codecs == ["av1", "h264", "hevc", "mpeg2", "vc1", "vp8", "vp9"]
