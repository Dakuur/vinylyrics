from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class ClockConfig:
    min_speed: float = 0.97
    max_speed: float = 1.03
    reject_threshold_sec: float = 3.0
    absorb_window_sec: float = 4.0
    max_history: int = 8

    def __post_init__(self) -> None:
        if self.absorb_window_sec * self.min_speed <= self.reject_threshold_sec:
            raise ValueError(
                "absorb_window_sec * min_speed must exceed reject_threshold_sec, "
                "otherwise a large accepted correction can make position() run "
                "backwards while it's being absorbed"
            )


class PlaybackClock:
    def __init__(self, config: ClockConfig = ClockConfig()):
        self._config = config
        self._speed = 1.0
        self._anchor_wall: "float | None" = None
        self._anchor_position: "float | None" = None
        self._history: list[tuple[float, float]] = []
        self._correction_start: "float | None" = None
        self._correction_error = 0.0

    @property
    def is_anchored(self) -> bool:
        return self._anchor_wall is not None

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def anchor_wall(self) -> "float | None":
        return self._anchor_wall

    @property
    def anchor_position(self) -> "float | None":
        return self._anchor_position

    def position(self, now: float) -> "float | None":
        if not self.is_anchored:
            return None
        base = self._speed * (now - self._anchor_wall) + self._anchor_position
        if self._correction_start is not None:
            elapsed = now - self._correction_start
            if elapsed < self._config.absorb_window_sec:
                remaining_fraction = 1.0 - elapsed / self._config.absorb_window_sec
                base -= self._correction_error * remaining_fraction
        return base

    def add_anchor(self, wall_time: float, position_sec: float, timeskew: float = 0.0) -> bool:
        """Record a Shazam recognition anchor.

        `wall_time` must be the wall-clock time at which the audio buffer that
        produced this recognition was CAPTURED — e.g. the start of the
        sliding window submitted for recognition — not the time the
        recognition response arrived. Per spec §5, using arrival time instead
        of capture time would make the position estimate lag by the full
        recognition round-trip latency. `position_sec` is the position within
        the track that the recognizer reported for that same buffer.

        Returns True if the anchor was accepted, False if it implied an
        unreasonably large jump (probable false match) and was ignored —
        in which case speed/history/anchor state are left unchanged.
        """
        cfg = self._config

        if not self.is_anchored:
            self._speed = _clamp(1.0 + timeskew, cfg.min_speed, cfg.max_speed)
            self._anchor_wall = wall_time
            self._anchor_position = position_sec
            self._history = [(wall_time, position_sec)]
            self._correction_start = None
            return True

        predicted = self.position(wall_time)
        error = position_sec - predicted
        if abs(error) > cfg.reject_threshold_sec:
            return False

        self._history.append((wall_time, position_sec))
        if len(self._history) > cfg.max_history:
            self._history = self._history[-cfg.max_history :]

        if len(self._history) >= 2:
            times = np.array([t for t, _ in self._history])
            positions = np.array([p for _, p in self._history])
            slope, _intercept = np.polyfit(times, positions, 1)
            self._speed = _clamp(float(slope), cfg.min_speed, cfg.max_speed)

        self._correction_start = wall_time
        self._correction_error = error
        self._anchor_wall = wall_time
        self._anchor_position = position_sec
        return True
