import pytest

from vinylyrics.audio.source import FileSource
from vinylyrics.recognition.enrich import recognize_with_cover_art
from vinylyrics.recognition.shazam import ShazamIORecognizer


@pytest.mark.network
def test_recognize_with_cover_art_at_production_sample_rate():
    """Exercises the real Shazam + MusicBrainz + Cover Art Archive pipeline
    at the actual 16kHz mono sample rate AudioSource produces in production
    (every other network test in this phase uses 44.1kHz files directly)."""
    source = FileSource("/home/dakur/Downloads/songs/Bonito.mp3", sample_rate=16000)
    source.read(30.0)  # skip ahead, same offset the other Bonito.mp3 tests use
    clip = source.read(12.0)

    recognizer = ShazamIORecognizer()
    result = _run(recognize_with_cover_art(recognizer, clip, 16000))

    assert result is not None
    assert "bonito" in result.title.lower()
    assert "jarabe" in result.artist.lower()
    assert result.cover_url is not None


def _run(coro):
    import asyncio
    return asyncio.run(coro)
