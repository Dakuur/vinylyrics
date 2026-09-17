import pytest

from vinylyrics.lyrics.lrclib import LrcLibClient


@pytest.mark.network
def test_fetch_finds_real_lyrics_via_search_fallback():
    client = LrcLibClient()
    # Deliberately wrong album/duration, matching what Shazam's real metadata
    # will realistically look like — this exercises the /get-404-then-/search
    # path, which is the one that actually works in practice (verified during
    # planning: /get 404s here every time, /search finds it).
    result = client.fetch("Jarabe de Palo", "Bonito", "Depende", 238.0)

    assert result is not None
    assert result.has_synced
    assert any("bonito" in line.text.lower() for line in result.synced_lines)
