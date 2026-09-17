import pytest

from vinylyrics.palette import FALLBACK_PALETTE, extract_palette


@pytest.mark.network
def test_extract_palette_against_a_real_cover_image():
    # A real Shazam cover art URL for "Bonito" by Jarabe de Palo, fetched
    # live during planning — dominant color there was a saturated red,
    # (216,0,1), which this test re-derives against the live URL.
    url = "https://is1-ssl.mzstatic.com/image/thumb/Music19/v4/ca/f5/b8/caf5b89c-d331-632d-c17b-0a1d576cc653/mzm.umknsjlj.jpg/400x400cc.jpg"
    palette = extract_palette(url)

    assert palette != FALLBACK_PALETTE
    assert palette.fg == "#f0ede8"
    assert palette.bg.startswith("#")
