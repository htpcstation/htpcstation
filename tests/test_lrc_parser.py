"""Tests for Task 001 — LRC Parser.

Covers:
  - parse_lrc: standard LRC line parsing with correct ms calculation
  - parse_lrc: multiple timestamps on one line emit one entry per timestamp
  - parse_lrc: header tags (non-timestamp lines) are ignored
  - parse_lrc: blank-text lines are included with text=""
  - parse_lrc: lines out of order in input → output sorted by ms
  - parse_lrc: empty string input → []
  - parse_lrc: None input → []
  - parse_plain: each non-empty line becomes {ms: -1, text: ...}
  - parse_plain: empty lines are skipped
  - parse_plain: empty string input → []
  - parse_plain: None input → []
"""

from __future__ import annotations

import pytest

from backend.lrc_parser import parse_lrc, parse_plain


# ---------------------------------------------------------------------------
# parse_lrc — standard line parsing
# ---------------------------------------------------------------------------


class TestParseLrcStandard:
    def test_single_line_ms_calculation(self) -> None:
        """ms = minutes*60000 + seconds*1000 + hundredths*10."""
        result = parse_lrc("[01:23.45] Hello world")
        assert result == [{"ms": 83_450, "text": "Hello world"}]

    def test_ms_calculation_zero_timestamp(self) -> None:
        result = parse_lrc("[00:00.00] Start")
        assert result == [{"ms": 0, "text": "Start"}]

    def test_ms_calculation_minutes_only(self) -> None:
        # 2 minutes = 120000 ms
        result = parse_lrc("[02:00.00] Two minutes")
        assert result == [{"ms": 120_000, "text": "Two minutes"}]

    def test_ms_calculation_hundredths(self) -> None:
        # 10 hundredths = 100 ms
        result = parse_lrc("[00:00.10] Hundredths")
        assert result == [{"ms": 100, "text": "Hundredths"}]

    def test_multiple_lines(self) -> None:
        lrc = "[00:01.00] Line one\n[00:02.00] Line two\n[00:03.00] Line three"
        result = parse_lrc(lrc)
        assert len(result) == 3
        assert result[0] == {"ms": 1_000, "text": "Line one"}
        assert result[1] == {"ms": 2_000, "text": "Line two"}
        assert result[2] == {"ms": 3_000, "text": "Line three"}


# ---------------------------------------------------------------------------
# parse_lrc — multiple timestamps on one line
# ---------------------------------------------------------------------------


class TestParseLrcMultipleTimestamps:
    def test_two_timestamps_same_line(self) -> None:
        """Each timestamp on a line emits a separate entry with the same text."""
        result = parse_lrc("[00:10.00][00:20.00] chorus")
        assert len(result) == 2
        assert {"ms": 10_000, "text": "chorus"} in result
        assert {"ms": 20_000, "text": "chorus"} in result

    def test_three_timestamps_same_line(self) -> None:
        result = parse_lrc("[00:05.00][00:15.00][00:25.00] refrain")
        assert len(result) == 3
        texts = [e["text"] for e in result]
        assert all(t == "refrain" for t in texts)
        ms_values = sorted(e["ms"] for e in result)
        assert ms_values == [5_000, 15_000, 25_000]


# ---------------------------------------------------------------------------
# parse_lrc — header tags ignored
# ---------------------------------------------------------------------------


class TestParseLrcHeaderTags:
    def test_artist_tag_ignored(self) -> None:
        result = parse_lrc("[ar:Some Artist]")
        assert result == []

    def test_title_tag_ignored(self) -> None:
        result = parse_lrc("[ti:Some Title]")
        assert result == []

    def test_album_tag_ignored(self) -> None:
        result = parse_lrc("[al:Some Album]")
        assert result == []

    def test_mixed_headers_and_lyrics(self) -> None:
        lrc = (
            "[ar:Artist]\n"
            "[ti:Title]\n"
            "[al:Album]\n"
            "[00:01.00] First lyric\n"
            "[00:02.00] Second lyric\n"
        )
        result = parse_lrc(lrc)
        assert len(result) == 2
        assert result[0]["text"] == "First lyric"
        assert result[1]["text"] == "Second lyric"


# ---------------------------------------------------------------------------
# parse_lrc — blank-text lines included
# ---------------------------------------------------------------------------


class TestParseLrcBlankTextLines:
    def test_blank_text_line_included(self) -> None:
        """A timestamp with only trailing space produces text='' after strip."""
        result = parse_lrc("[01:23.45] ")
        assert len(result) == 1
        assert result[0]["ms"] == 83_450
        assert result[0]["text"] == ""

    def test_blank_text_line_no_space(self) -> None:
        """A timestamp immediately at end of line produces text=''."""
        result = parse_lrc("[01:23.45]")
        assert len(result) == 1
        assert result[0]["ms"] == 83_450
        assert result[0]["text"] == ""

    def test_blank_lines_mixed_with_lyrics(self) -> None:
        lrc = "[00:01.00] Verse\n[00:02.00]\n[00:03.00] Chorus"
        result = parse_lrc(lrc)
        assert len(result) == 3
        assert result[1] == {"ms": 2_000, "text": ""}


# ---------------------------------------------------------------------------
# parse_lrc — out-of-order input sorted by ms
# ---------------------------------------------------------------------------


class TestParseLrcSorting:
    def test_out_of_order_sorted_ascending(self) -> None:
        lrc = "[00:30.00] Third\n[00:10.00] First\n[00:20.00] Second"
        result = parse_lrc(lrc)
        assert result[0] == {"ms": 10_000, "text": "First"}
        assert result[1] == {"ms": 20_000, "text": "Second"}
        assert result[2] == {"ms": 30_000, "text": "Third"}

    def test_already_sorted_unchanged(self) -> None:
        lrc = "[00:01.00] A\n[00:02.00] B\n[00:03.00] C"
        result = parse_lrc(lrc)
        ms_values = [e["ms"] for e in result]
        assert ms_values == sorted(ms_values)


# ---------------------------------------------------------------------------
# parse_lrc — empty / None input
# ---------------------------------------------------------------------------


class TestParseLrcEmptyInput:
    def test_empty_string_returns_empty_list(self) -> None:
        assert parse_lrc("") == []

    def test_none_returns_empty_list(self) -> None:
        assert parse_lrc(None) == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert parse_lrc("   \n\n  ") == []

    def test_only_header_tags_returns_empty_list(self) -> None:
        assert parse_lrc("[ar:Artist]\n[ti:Title]") == []


# ---------------------------------------------------------------------------
# parse_plain — basic behaviour
# ---------------------------------------------------------------------------


class TestParsePlain:
    def test_each_non_empty_line_becomes_entry(self) -> None:
        result = parse_plain("Line one\nLine two\nLine three")
        assert result == [
            {"ms": -1, "text": "Line one"},
            {"ms": -1, "text": "Line two"},
            {"ms": -1, "text": "Line three"},
        ]

    def test_empty_lines_skipped(self) -> None:
        result = parse_plain("Line one\n\nLine two\n\n\nLine three")
        assert len(result) == 3
        assert result[0]["text"] == "Line one"
        assert result[1]["text"] == "Line two"
        assert result[2]["text"] == "Line three"

    def test_all_ms_are_minus_one(self) -> None:
        result = parse_plain("A\nB\nC")
        assert all(e["ms"] == -1 for e in result)

    def test_single_line(self) -> None:
        result = parse_plain("Only line")
        assert result == [{"ms": -1, "text": "Only line"}]


# ---------------------------------------------------------------------------
# parse_plain — empty / None input
# ---------------------------------------------------------------------------


class TestParsePlainEmptyInput:
    def test_empty_string_returns_empty_list(self) -> None:
        assert parse_plain("") == []

    def test_none_returns_empty_list(self) -> None:
        assert parse_plain(None) == []

    def test_only_empty_lines_returns_empty_list(self) -> None:
        assert parse_plain("\n\n\n") == []
