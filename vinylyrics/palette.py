from __future__ import annotations

import colorsys
import io
from dataclasses import dataclass

import requests
from PIL import Image

COVER_TIMEOUT_SEC = 5.0
MIN_CONTRAST = 7.0
TARGET_MIN_L = 0.12
TARGET_MAX_L = 0.20
MAX_SATURATION = 0.5
FG_RGB = (0xF0, 0xED, 0xE8)


@dataclass(frozen=True)
class Palette:
    bg: str
    fg: str
    dim: str


def _hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


FALLBACK_PALETTE = Palette(bg="#1a2733", fg=_hex(FG_RGB), dim="#8a99a5")


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def lin(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    l1 = _relative_luminance(rgb1) + 0.05
    l2 = _relative_luminance(rgb2) + 0.05
    return max(l1, l2) / min(l1, l2)


def _dominant_rgb_from_bytes(image_bytes: bytes) -> tuple[int, int, int]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((100, 100))
    quantized = img.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    counts = sorted(quantized.getcolors(), reverse=True)
    top_index = counts[0][1]
    palette_bytes = quantized.getpalette()
    r, g, b = palette_bytes[top_index * 3 : top_index * 3 + 3]
    return r, g, b


def _force_projectable(r: int, g: int, b: int) -> tuple[int, int, int]:
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    l = min(max(l, TARGET_MIN_L), TARGET_MAX_L)
    s = min(s, MAX_SATURATION)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return round(r2 * 255), round(g2 * 255), round(b2 * 255)


def _darken_until_contrast(rgb: tuple[int, int, int], fg_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    h, l, s = colorsys.rgb_to_hls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    while l > 0.0:
        candidate = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))
        if _contrast_ratio(fg_rgb, candidate) >= MIN_CONTRAST:
            return candidate
        l -= 0.01
    return (0, 0, 0)


def _blend(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int], weight: float) -> tuple[int, int, int]:
    return tuple(round(c1 * (1 - weight) + c2 * weight) for c1, c2 in zip(rgb1, rgb2))


def extract_palette(cover_url: "str | None") -> Palette:
    if not cover_url:
        return FALLBACK_PALETTE
    try:
        response = requests.get(cover_url, timeout=COVER_TIMEOUT_SEC)
        response.raise_for_status()
        dominant = _dominant_rgb_from_bytes(response.content)
    except Exception:
        return FALLBACK_PALETTE

    projectable = _force_projectable(*dominant)
    bg_rgb = _darken_until_contrast(projectable, FG_RGB)
    dim_rgb = _blend(bg_rgb, FG_RGB, weight=0.45)
    return Palette(bg=_hex(bg_rgb), fg=_hex(FG_RGB), dim=_hex(dim_rgb))
