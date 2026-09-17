import pytest

from vinylyrics.recognition.cover_art import find_cover_url


@pytest.mark.network
def test_find_cover_url_finds_a_real_release():
    url = find_cover_url("Jarabe de Palo", "Bonito", isrc="ES96A0800012")
    assert url is not None
    assert url.startswith("https://coverartarchive.org/release/")
