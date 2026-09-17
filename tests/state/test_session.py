import pytest

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import LyricLine
from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.state.session import DisplayState, PlaybackSession


def _result(title="Bonito", artist="Jarabe de Palo", duration=238.0, offset=27.79) -> RecognitionResult:
    return RecognitionResult(
        title=title, artist=artist, album="Depende", cover_url="https://example.com/cover.jpg",
        offset=offset, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1", duration=duration,
    )


def _lyrics() -> LyricsResult:
    return LyricsResult(
        synced_lines=(LyricLine(ms=1000, text="hola"), LyricLine(ms=2000, text="mundo")),
        plain_lyrics=None, instrumental=False,
    )


def test_session_starts_idle():
    session = PlaybackSession()
    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.IDLE
    assert payload["track"] is None
    assert payload["clock"] is None
    assert payload["lyrics"] == []


def test_on_listening_started_sets_listening_with_no_track():
    session = PlaybackSession()
    session.on_listening_started()
    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.LISTENING
    assert payload["track"] is None


def test_on_recognized_sets_playing_with_track_and_lyrics():
    session = PlaybackSession()
    session.on_recognized(_result(), _lyrics(), wall_time=100.0)
    payload = session.to_payload(now=100.0)

    assert payload["state"] == DisplayState.PLAYING
    assert payload["track"]["title"] == "Bonito"
    assert payload["track"]["artist"] == "Jarabe de Palo"
    assert payload["track"]["album"] == "Depende"
    assert payload["track"]["cover_url"] == "https://example.com/cover.jpg"
    assert payload["lyrics"] == [{"ms": 1000, "text": "hola"}, {"ms": 2000, "text": "mundo"}]
    assert payload["clock"]["anchor_wall"] == 100.0
    assert payload["clock"]["anchor_ms"] == pytest.approx(27790.0, abs=1.0)
    assert payload["clock"]["speed"] == pytest.approx(1.0)
    assert payload["palette"]["fg"] == "#f0ede8"


def test_on_recognized_same_track_extends_existing_clock_not_a_new_one():
    session = PlaybackSession()
    session.on_recognized(_result(offset=27.79), _lyrics(), wall_time=0.0)

    # A second recognition of the SAME song 10s later, with the offset
    # advanced roughly by real playback time (~1x speed). Verified live
    # during planning: reusing the SAME offset unchanged here (as if the
    # song hadn't moved) makes this anchor imply the song jumped BACKWARDS
    # by 10s relative to the first anchor's prediction — PlaybackClock's
    # own >3s-jump guard then correctly REJECTS it, and this test's later
    # assertion (`anchor_wall == 10.0`) fails because nothing was accepted.
    # The fixture must advance the offset to stay inside the accepted range.
    second = _result(offset=37.79)
    session.on_recognized(second, _lyrics(), wall_time=10.0)
    # position() from the clock should reflect a real anchor history spanning
    # both calls, not a from-scratch single-anchor clock
    payload = session.to_payload(now=10.0)
    assert payload["state"] == DisplayState.PLAYING
    assert payload["clock"]["anchor_wall"] == 10.0


def test_on_recognized_different_track_starts_a_fresh_clock():
    session = PlaybackSession()
    session.on_recognized(_result(title="Bonito"), _lyrics(), wall_time=0.0)
    session.on_recognized(_result(title="Other Song"), _lyrics(), wall_time=500.0)

    payload = session.to_payload(now=500.0)
    assert payload["track"]["title"] == "Other Song"
    assert payload["clock"]["anchor_wall"] == 500.0


def test_on_recognized_with_no_synced_lyrics_still_shows_track():
    session = PlaybackSession()
    unsynced = LyricsResult(synced_lines=(), plain_lyrics="letra sin sincronizar", instrumental=False)
    session.on_recognized(_result(), unsynced, wall_time=0.0)

    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.PLAYING
    assert payload["lyrics"] == []  # no karaoke, but the track/palette still show


def test_on_recognized_with_no_lyrics_result_at_all():
    session = PlaybackSession()
    session.on_recognized(_result(), None, wall_time=0.0)

    payload = session.to_payload(now=0.0)
    assert payload["lyrics"] == []


def test_on_unidentified_sets_state_without_clearing_nothing_to_clear():
    session = PlaybackSession()
    session.on_unidentified()
    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.UNIDENTIFIED
    assert payload["track"] is None


def test_on_stopped_clears_track_and_returns_to_idle():
    session = PlaybackSession()
    session.on_recognized(_result(), _lyrics(), wall_time=0.0)
    session.on_stopped()

    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.IDLE
    assert payload["track"] is None
    assert payload["clock"] is None
    assert payload["lyrics"] == []


def test_on_track_gap_does_not_clear_the_current_track():
    session = PlaybackSession()
    session.on_recognized(_result(), _lyrics(), wall_time=0.0)
    session.on_track_gap()

    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.PLAYING
    assert payload["track"]["title"] == "Bonito"


def test_on_recognized_without_explicit_palette_uses_fallback():
    from vinylyrics.palette import FALLBACK_PALETTE

    session = PlaybackSession()
    session.on_recognized(_result(), _lyrics(), wall_time=0.0)
    payload = session.to_payload(now=0.0)
    assert payload["palette"]["bg"] == FALLBACK_PALETTE.bg


def test_on_recognized_uses_explicit_palette_when_given():
    from vinylyrics.palette import Palette

    session = PlaybackSession()
    custom = Palette(bg="#112233", fg="#f0ede8", dim="#556677")
    session.on_recognized(_result(), _lyrics(), wall_time=0.0, palette=custom)
    payload = session.to_payload(now=0.0)
    assert payload["palette"]["bg"] == "#112233"


def test_is_same_track_reflects_current_track():
    session = PlaybackSession()
    assert session.is_same_track(_result(title="Bonito")) is False
    session.on_recognized(_result(title="Bonito"), _lyrics(), wall_time=0.0)
    assert session.is_same_track(_result(title="Bonito")) is True
    assert session.is_same_track(_result(title="Other")) is False
