from __future__ import annotations

import asyncio

import musicbrainzngs as mb
import requests

# Must stay in sync with .env.example's VINYLYRICS_USER_AGENT
# ("vinylyrics/0.1 (+https://github.com/Dakuur/vinylyrics)") — MusicBrainz's
# client wants app/version/contact as three separate fields rather than one
# combined string, so this hardcodes the same values instead of parsing the
# env var apart.
mb.set_useragent("vinylyrics", "0.1", "https://github.com/Dakuur/vinylyrics")

CAA_TIMEOUT_SEC = 5.0
MIN_SEARCH_SCORE = 90


def _mbids_from_isrc(isrc: str) -> list[str]:
    try:
        result = mb.get_recordings_by_isrc(isrc, includes=["releases"])
    except mb.MusicBrainzError:
        return []
    mbids = []
    for rec in result.get("isrc", {}).get("recording-list", []):
        for rel in rec.get("release-list", []):
            mbids.append(rel["id"])
    return mbids


def _mbids_from_search(artist: str, title: str, album: "str | None" = None) -> list[str]:
    search_kwargs = {"recording": title, "artist": artist, "limit": 10}
    if album:
        search_kwargs["release"] = album
    try:
        result = mb.search_recordings(**search_kwargs)
    except mb.MusicBrainzError:
        return []
    mbids = []
    for rec in result.get("recording-list", []):
        score = int(rec.get("ext:score", 0))
        if score < MIN_SEARCH_SCORE:
            continue
        for rel in rec.get("release-list", []):
            mbids.append(rel["id"])
    return mbids


def _caa_front_url_if_exists(mbid: str) -> "str | None":
    url = f"https://coverartarchive.org/release/{mbid}/front"
    try:
        response = requests.head(url, allow_redirects=True, timeout=CAA_TIMEOUT_SEC)
    except requests.RequestException:
        return None
    return url if response.status_code == 200 else None


def find_cover_url(artist: str, title: str, album: "str | None" = None, isrc: "str | None" = None) -> "str | None":
    mbids = []
    if isrc:
        mbids.extend(_mbids_from_isrc(isrc))
    if not mbids:
        mbids.extend(_mbids_from_search(artist, title, album))

    for mbid in mbids:
        url = _caa_front_url_if_exists(mbid)
        if url is not None:
            return url
    return None


async def find_cover_url_async(
    artist: str, title: str, album: "str | None" = None, isrc: "str | None" = None
) -> "str | None":
    return await asyncio.to_thread(find_cover_url, artist, title, album, isrc)
