from __future__ import annotations

import re
from dataclasses import dataclass

_TIMESTAMP_RE = re.compile(r"\[(\d{2,}):(\d{2})[.:](\d{2,3})\]")


@dataclass(frozen=True)
class LyricLine:
    ms: int
    text: str


def _timestamp_to_ms(minutes: str, seconds: str, fraction: str) -> int:
    frac_digits = len(fraction)
    frac_value = int(fraction) * (10 ** (3 - frac_digits)) if frac_digits <= 3 else int(fraction[:3])
    return int(minutes) * 60_000 + int(seconds) * 1_000 + frac_value


def parse_lrc(text: str) -> list[LyricLine]:
    lines: list[LyricLine] = []
    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        timestamps = list(_TIMESTAMP_RE.finditer(raw_line))
        if not timestamps:
            continue  # metadata tag like [ar:...] or a stray non-lyric line
        lyric_text = _TIMESTAMP_RE.sub("", raw_line).strip()
        for m in timestamps:
            ms = _timestamp_to_ms(m.group(1), m.group(2), m.group(3))
            lines.append(LyricLine(ms=ms, text=lyric_text))
    lines.sort(key=lambda l: l.ms)
    return lines
