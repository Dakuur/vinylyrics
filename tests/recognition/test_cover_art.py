from unittest import mock

from vinylyrics.recognition import cover_art


def _fake_head_response(status_code: int):
    resp = mock.MagicMock()
    resp.status_code = status_code
    return resp


def test_find_cover_url_uses_isrc_when_available():
    isrc_result = {"isrc": {"recording-list": [{"release-list": [{"id": "mbid-from-isrc"}]}]}}
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", return_value=isrc_result) as isrc_mock, \
         mock.patch.object(cover_art.mb, "search_recordings") as search_mock, \
         mock.patch.object(cover_art.requests, "head", return_value=_fake_head_response(200)):
        url = cover_art.find_cover_url("Artist", "Title", isrc="US1234567890")

    isrc_mock.assert_called_once()
    search_mock.assert_not_called()
    assert url == "https://coverartarchive.org/release/mbid-from-isrc/front"


def test_find_cover_url_falls_back_to_search_when_isrc_lookup_fails():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(
             cover_art.mb, "search_recordings",
             return_value={
                 "recording-list": [
                     {
                         "ext:score": "95",
                         "title": "Title",
                         "artist-credit": [{"artist": {"name": "Artist"}}],
                         "release-list": [{"id": "mbid-from-search"}],
                     }
                 ]
             },
         ) as search_mock, \
         mock.patch.object(cover_art.requests, "head", return_value=_fake_head_response(200)):
        url = cover_art.find_cover_url("Artist", "Title", isrc="US1234567890")

    search_mock.assert_called_once()
    assert url == "https://coverartarchive.org/release/mbid-from-search/front"


def test_find_cover_url_skips_low_score_search_results():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(
             cover_art.mb, "search_recordings",
             return_value={"recording-list": [{"ext:score": "40", "release-list": [{"id": "low-score-mbid"}]}]},
         ), \
         mock.patch.object(cover_art.requests, "head") as head_mock:
        url = cover_art.find_cover_url("Artist", "Title")

    head_mock.assert_not_called()
    assert url is None


def test_find_cover_url_tries_next_mbid_when_first_has_no_cover_art():
    search_result = {
        "recording-list": [
            {
                "ext:score": "95",
                "title": "Title",
                "artist-credit": [{"artist": {"name": "Artist"}}],
                "release-list": [{"id": "mbid-no-art"}, {"id": "mbid-with-art"}],
            },
        ]
    }
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value=search_result), \
         mock.patch.object(cover_art.requests, "head", side_effect=[_fake_head_response(404), _fake_head_response(200)]):
        url = cover_art.find_cover_url("Artist", "Title")

    assert url == "https://coverartarchive.org/release/mbid-with-art/front"


def test_find_cover_url_returns_none_when_nothing_found():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value={"recording-list": []}), \
         mock.patch.object(cover_art.requests, "head") as head_mock:
        url = cover_art.find_cover_url("Artist", "Title")

    head_mock.assert_not_called()
    assert url is None


def test_find_cover_url_handles_network_error_gracefully():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(
             cover_art.mb, "search_recordings",
             return_value={
                 "recording-list": [
                     {
                         "ext:score": "95",
                         "title": "Title",
                         "artist-credit": [{"artist": {"name": "Artist"}}],
                         "release-list": [{"id": "some-mbid"}],
                     }
                 ]
             },
         ), \
         mock.patch.object(cover_art.requests, "head", side_effect=cover_art.requests.RequestException("timeout")):
        url = cover_art.find_cover_url("Artist", "Title")

    assert url is None


def test_find_cover_url_rejects_wrong_song_despite_high_score():
    search_result = {
        "recording-list": [
            {
                "ext:score": "100",
                "title": "El Bosque de Palo",
                "artist-credit": [{"artist": {"name": "Jarabe de Palo"}}],
                "release-list": [{"id": "wrong-song-mbid"}],
            },
            {
                "ext:score": "99",
                "title": "Bonito",
                "artist-credit": [{"artist": {"name": "Jarabe de Palo"}}],
                "release-list": [{"id": "right-song-mbid"}],
            },
        ]
    }
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value=search_result), \
         mock.patch.object(cover_art.requests, "head", return_value=_fake_head_response(200)):
        url = cover_art.find_cover_url("Jarabe de Palo", "Bonito")

    assert url == "https://coverartarchive.org/release/right-song-mbid/front"


def test_find_cover_url_rejects_same_title_different_artist():
    search_result = {
        "recording-list": [
            {
                "ext:score": "100",
                "title": "Mucho mejor",
                "artist-credit": [{"artist": {"name": "Los Argentinos"}}],
                "release-list": [{"id": "wrong-artist-mbid"}],
            },
            {
                "ext:score": "91",
                "title": "Mucho mejor",
                "artist-credit": [{"artist": {"name": "Los Rodríguez"}}],
                "release-list": [{"id": "right-artist-mbid"}],
            },
        ]
    }
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value=search_result), \
         mock.patch.object(cover_art.requests, "head", return_value=_fake_head_response(200)):
        url = cover_art.find_cover_url("Los Rodríguez", "Mucho mejor")

    assert url == "https://coverartarchive.org/release/right-artist-mbid/front"


def test_find_track_duration_uses_isrc_when_available():
    isrc_result = {"isrc": {"recording-list": [{"length": "238000"}]}}
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", return_value=isrc_result) as isrc_mock, \
         mock.patch.object(cover_art.mb, "search_recordings") as search_mock:
        duration = cover_art.find_track_duration("Artist", "Title", isrc="ISRC1")

    assert duration == 238.0
    isrc_mock.assert_called_once()
    search_mock.assert_not_called()


def test_find_track_duration_falls_back_to_search_when_isrc_lookup_fails():
    search_result = {
        "recording-list": [
            {"title": "Title", "artist-credit": [{"artist": {"name": "Artist"}}], "ext:score": "100", "length": "200000"},
        ]
    }
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value=search_result) as search_mock:
        duration = cover_art.find_track_duration("Artist", "Title")

    assert duration == 200.0
    search_mock.assert_called_once()


def test_find_track_duration_skips_low_score_and_mismatched_results():
    search_result = {
        "recording-list": [
            {"title": "Title", "artist-credit": [{"artist": {"name": "Artist"}}], "ext:score": "50", "length": "200000"},
            {"title": "Different Song", "artist-credit": [{"artist": {"name": "Artist"}}], "ext:score": "100", "length": "999000"},
            {"title": "Title", "artist-credit": [{"artist": {"name": "Artist"}}], "ext:score": "95", "length": "205000"},
        ]
    }
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value=search_result):
        duration = cover_art.find_track_duration("Artist", "Title")

    assert duration == 205.0  # skips the low-score row and the title mismatch


def test_find_track_duration_returns_none_when_nothing_matches():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value={"recording-list": []}):
        duration = cover_art.find_track_duration("Artist", "Title")

    assert duration is None


def test_find_track_duration_handles_network_error_gracefully():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", side_effect=cover_art.mb.MusicBrainzError("boom")):
        duration = cover_art.find_track_duration("Artist", "Title")

    assert duration is None
