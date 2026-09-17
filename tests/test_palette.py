import colorsys

import pytest

from vinylyrics.palette import FALLBACK_PALETTE, Palette, _contrast_ratio, _dominant_rgb_from_bytes, _force_projectable, extract_palette


def _make_test_jpeg_bytes(rgb: tuple[int, int, int]) -> bytes:
    import io
    from PIL import Image

    img = Image.new("RGB", (50, 50), rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_extract_palette_returns_fallback_when_no_cover_url():
    palette = extract_palette(None)
    assert palette == FALLBACK_PALETTE


def test_extract_palette_returns_fallback_on_download_failure(monkeypatch):
    import vinylyrics.palette as palette_module

    def _raise(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr(palette_module.requests, "get", _raise)
    palette = extract_palette("https://example.com/cover.jpg")
    assert palette == FALLBACK_PALETTE


def test_extract_palette_downloads_and_extracts_dominant_color(monkeypatch):
    import vinylyrics.palette as palette_module

    class _FakeResponse:
        content = _make_test_jpeg_bytes((30, 60, 200))  # a mid-blue, already dark

        def raise_for_status(self):
            pass

    monkeypatch.setattr(palette_module.requests, "get", lambda *a, **k: _FakeResponse())
    palette = extract_palette("https://example.com/cover.jpg")

    assert palette.bg.startswith("#")
    assert palette.fg == "#f0ede8"
    assert palette != FALLBACK_PALETTE


def test_dominant_rgb_from_bytes_finds_the_solid_fill_color():
    jpeg_bytes = _make_test_jpeg_bytes((10, 200, 80))
    r, g, b = _dominant_rgb_from_bytes(jpeg_bytes)
    # JPEG is lossy, allow a small tolerance
    assert abs(r - 10) < 15
    assert abs(g - 200) < 15
    assert abs(b - 80) < 15


def test_force_projectable_clamps_lightness_and_saturation():
    # a very bright, fully-saturated color: h doesn't matter for this check
    r, g, b = _force_projectable(255, 0, 0)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    # rounding to 8-bit RGB and back introduces small quantization error —
    # verified live during planning: clamping to exactly s=0.5 then
    # round-tripping through 8-bit RGB recovers s=0.5098, not exactly 0.5.
    # A 0.02 tolerance absorbs that without masking a real clamp failure
    # (the unclamped input here is fully saturated red, s=1.0 — an order
    # of magnitude past this tolerance if the clamp weren't applied).
    assert 0.12 - 0.02 <= l <= 0.20 + 0.02
    assert s <= 0.5 + 0.02


def test_force_projectable_raises_lightness_when_original_is_darker_than_range():
    r, g, b = _force_projectable(5, 5, 5)  # near-black
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    assert l >= 0.12 - 1e-6


def test_contrast_ratio_of_black_and_white_is_maximal():
    ratio = _contrast_ratio((255, 255, 255), (0, 0, 0))
    assert ratio == pytest.approx(21.0, abs=0.01)


def test_extract_palette_always_passes_wcag_contrast_against_fg():
    import vinylyrics.palette as palette_module

    # scan every hue at the clamp's least-favorable corner (l=0.20, s=0.5)
    # and confirm the final bg the module would emit always clears 7:1 —
    # this is the same scan run live during planning, now as a regression test.
    fg_rgb = (0xF0, 0xED, 0xE8)
    for hue_deg in range(0, 360, 15):
        h = hue_deg / 360
        r, g, b = (round(c * 255) for c in colorsys.hls_to_rgb(h, 0.20, 0.5))
        darkened = palette_module._darken_until_contrast((r, g, b), fg_rgb)
        assert _contrast_ratio(fg_rgb, darkened) >= 7.0 - 1e-6
