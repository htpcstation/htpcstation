"""Data models for Plex Media Server content.

Plain Python dataclasses — not QObjects. Parsed from Plex API JSON responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlexMovie:
    """Represents a single movie from the Plex library."""

    rating_key: str          # unique ID, e.g. "126522"
    title: str
    year: int = 0
    summary: str = ""
    content_rating: str = ""  # e.g. "PG"
    audience_rating: float = 0.0
    duration_ms: int = 0      # milliseconds
    studio: str = ""
    tagline: str = ""
    thumb_path: str = ""      # e.g. "/library/metadata/126522/thumb/1771639193"
    art_path: str = ""        # backdrop
    genres: list[str] = field(default_factory=list)
    directors: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    added_at: int = 0         # unix timestamp
    view_offset: int = 0      # resume position in ms (from on-deck)
    poster_local: str = ""    # local cached file:// URL (set by poster_cache)


@dataclass
class PlexShow:
    """Represents a TV show from the Plex library."""

    rating_key: str
    title: str
    year: int = 0
    summary: str = ""
    content_rating: str = ""
    audience_rating: float = 0.0
    thumb_path: str = ""
    art_path: str = ""
    genres: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    child_count: int = 0      # number of seasons
    leaf_count: int = 0       # total episodes
    viewed_leaf_count: int = 0
    poster_local: str = ""


@dataclass
class PlexSeason:
    """Represents a season of a TV show."""

    rating_key: str
    title: str                # e.g. "Season 1"
    index: int = 0            # season number
    thumb_path: str = ""
    leaf_count: int = 0       # episodes in this season
    viewed_leaf_count: int = 0
    parent_rating_key: str = ""  # show's rating_key


@dataclass
class PlexEpisode:
    """Represents a single episode of a TV show."""

    rating_key: str
    title: str
    index: int = 0            # episode number
    parent_index: int = 0     # season number
    summary: str = ""
    thumb_path: str = ""
    duration_ms: int = 0
    view_offset: int = 0      # resume position in ms
    viewed: bool = False      # fully watched
    grandparent_title: str = ""  # show title
    poster_local: str = ""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_movie(data: dict) -> PlexMovie:
    """Parse a Plex API JSON dict into a PlexMovie dataclass."""
    genres = [g["tag"] for g in data.get("Genre", []) if "tag" in g]
    directors = [d["tag"] for d in data.get("Director", []) if "tag" in d]
    cast = [r["tag"] for r in data.get("Role", []) if "tag" in r][:5]

    return PlexMovie(
        rating_key=str(data.get("ratingKey", "")),
        title=data.get("title", ""),
        year=int(data.get("year", 0) or 0),
        summary=data.get("summary", ""),
        content_rating=data.get("contentRating", ""),
        audience_rating=float(data.get("audienceRating", 0.0) or 0.0),
        duration_ms=int(data.get("duration", 0) or 0),
        studio=data.get("studio", ""),
        tagline=data.get("tagline", ""),
        thumb_path=data.get("thumb", ""),
        art_path=data.get("art", ""),
        genres=genres,
        directors=directors,
        cast=cast,
        added_at=int(data.get("addedAt", 0) or 0),
        view_offset=int(data.get("viewOffset", 0) or 0),
    )


def parse_show(data: dict) -> PlexShow:
    """Parse a Plex API JSON dict into a PlexShow dataclass."""
    genres = [g["tag"] for g in data.get("Genre", []) if "tag" in g]
    cast = [r["tag"] for r in data.get("Role", []) if "tag" in r][:5]

    return PlexShow(
        rating_key=str(data.get("ratingKey", "")),
        title=data.get("title", ""),
        year=int(data.get("year", 0) or 0),
        summary=data.get("summary", ""),
        content_rating=data.get("contentRating", ""),
        audience_rating=float(data.get("audienceRating", 0.0) or 0.0),
        thumb_path=data.get("thumb", ""),
        art_path=data.get("art", ""),
        genres=genres,
        cast=cast,
        child_count=int(data.get("childCount", 0) or 0),
        leaf_count=int(data.get("leafCount", 0) or 0),
        viewed_leaf_count=int(data.get("viewedLeafCount", 0) or 0),
    )


def parse_season(data: dict) -> PlexSeason:
    """Parse a Plex API JSON dict into a PlexSeason dataclass."""
    return PlexSeason(
        rating_key=str(data.get("ratingKey", "")),
        title=data.get("title", ""),
        index=int(data.get("index", 0) or 0),
        thumb_path=data.get("thumb", ""),
        leaf_count=int(data.get("leafCount", 0) or 0),
        viewed_leaf_count=int(data.get("viewedLeafCount", 0) or 0),
        parent_rating_key=str(data.get("parentRatingKey", "")),
    )


def parse_episode(data: dict) -> PlexEpisode:
    """Parse a Plex API JSON dict into a PlexEpisode dataclass."""
    # An episode is considered fully watched if viewCount > 0 and no viewOffset
    view_count = int(data.get("viewCount", 0) or 0)
    view_offset = int(data.get("viewOffset", 0) or 0)
    viewed = view_count > 0 and view_offset == 0

    return PlexEpisode(
        rating_key=str(data.get("ratingKey", "")),
        title=data.get("title", ""),
        index=int(data.get("index", 0) or 0),
        parent_index=int(data.get("parentIndex", 0) or 0),
        summary=data.get("summary", ""),
        thumb_path=data.get("thumb", ""),
        duration_ms=int(data.get("duration", 0) or 0),
        view_offset=view_offset,
        viewed=viewed,
        grandparent_title=data.get("grandparentTitle", ""),
    )


# ---------------------------------------------------------------------------
# Music models
# ---------------------------------------------------------------------------


@dataclass
class PlexArtist:
    """Represents a music artist from the Plex library."""

    rating_key: str
    title: str          # artist name
    summary: str = ""
    thumb_path: str = ""
    genre: str = ""     # comma-joined genres
    poster_local: str = ""


@dataclass
class PlexAlbum:
    """Represents a music album from the Plex library."""

    rating_key: str
    title: str          # album name
    year: int = 0
    thumb_path: str = ""
    leaf_count: int = 0       # track count
    parent_rating_key: str = ""  # artist's ratingKey
    parent_title: str = ""       # artist name
    poster_local: str = ""
    summary: str = ""
    studio: str = ""
    genre: str = ""     # comma-joined genres
    rating: float = 0.0


@dataclass
class PlexTrack:
    """Represents a music track from the Plex library."""

    rating_key: str
    title: str          # track name
    index: int = 0      # track number
    duration_ms: int = 0
    parent_title: str = ""       # album name
    grandparent_title: str = ""  # artist name
    media_key: str = ""          # /library/parts/... path for streaming
    codec_info: str = ""         # e.g. "FLAC 44.1/16", "MP3 320"


# ---------------------------------------------------------------------------
# Music parsing helpers
# ---------------------------------------------------------------------------


def parse_artist(data: dict) -> PlexArtist:
    """Parse a Plex API JSON dict into a PlexArtist dataclass."""
    raw_genres = data.get("Genre") or []
    genres = [g["tag"] for g in raw_genres if isinstance(g, dict) and "tag" in g]
    return PlexArtist(
        rating_key=str(data.get("ratingKey", "")),
        title=data.get("title", ""),
        summary=data.get("summary", ""),
        thumb_path=data.get("thumb", ""),
        genre=", ".join(genres),
    )


def parse_album(data: dict) -> PlexAlbum:
    """Parse a Plex API JSON dict into a PlexAlbum dataclass."""
    raw_genres = data.get("Genre") or []
    genres = [g["tag"] for g in raw_genres if isinstance(g, dict) and "tag" in g]
    return PlexAlbum(
        rating_key=str(data.get("ratingKey", "")),
        title=data.get("title", ""),
        year=int(data.get("year", 0) or 0),
        thumb_path=data.get("thumb", ""),
        leaf_count=int(data.get("leafCount", 0) or 0),
        parent_rating_key=str(data.get("parentRatingKey", "")),
        parent_title=data.get("parentTitle", ""),
        summary=data.get("summary", ""),
        studio=data.get("studio", ""),
        genre=", ".join(genres),
        rating=float(data.get("rating", 0) or 0) / 10.0,
    )


def parse_track(data: dict) -> PlexTrack:
    """Parse a Plex API JSON dict into a PlexTrack dataclass."""
    # Extract the streaming path and codec info from Media[0]
    media_key = ""
    codec_info = ""
    media_list = data.get("Media") or []
    if media_list and isinstance(media_list[0], dict):
        media = media_list[0]
        parts = media.get("Part") or []
        if parts and isinstance(parts[0], dict):
            media_key = parts[0].get("key", "")
        codec_info = _format_plex_codec_info(media)
    return PlexTrack(
        rating_key=str(data.get("ratingKey", "")),
        title=data.get("title", ""),
        index=int(data.get("index", 0) or 0),
        duration_ms=int(data.get("duration", 0) or 0),
        parent_title=data.get("parentTitle", ""),
        grandparent_title=data.get("grandparentTitle", ""),
        media_key=media_key,
        codec_info=codec_info,
    )


def _format_plex_codec_info(media: dict) -> str:
    """Build a codec summary from a Plex Media dict.

    Plex Media dict fields: audioCodec, bitrate, audioChannels,
    plus nested Stream entries with samplingRate, bitDepth.
    """
    codec_raw = (media.get("audioCodec") or media.get("container") or "").lower()
    codec_map = {
        "flac": "FLAC", "mp3": "MP3", "aac": "AAC", "opus": "OPUS",
        "vorbis": "OGG", "ogg": "OGG", "wav": "WAV", "wma": "WMA",
        "alac": "ALAC", "aiff": "AIFF", "pcm": "PCM",
    }
    codec = codec_map.get(codec_raw, codec_raw.upper())
    if not codec:
        return ""

    # Lossless: try to find sample rate and bit depth from Stream entries
    if codec in ("FLAC", "ALAC", "WAV", "AIFF", "PCM"):
        streams = media.get("Part", [{}])[0].get("Stream") if media.get("Part") else None
        sample_rate = 0
        bit_depth = 0
        if streams:
            for s in streams:
                if s.get("streamType") == 2:  # audio stream
                    sample_rate = int(s.get("samplingRate", 0) or 0)
                    bit_depth = int(s.get("bitDepth", 0) or 0)
                    break
        if sample_rate:
            sr = sample_rate / 1000
            sr_str = f"{sr:g}"
            if bit_depth:
                return f"{codec} {sr_str}/{bit_depth}"
            return f"{codec} {sr_str}"

    # Lossy: show bitrate
    bitrate = int(media.get("bitrate", 0) or 0)
    if bitrate:
        return f"{codec} {bitrate}"

    return codec
