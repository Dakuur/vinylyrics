from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CadenceConfig:
    min_interval_sec: float = 8.0
    resync_interval_sec: float = 45.0


class CallCadencePolicy:
    def __init__(self, config: CadenceConfig = CadenceConfig()):
        self._config = config
        self._last_call_at: "float | None" = None
        self._locked = False
        self._in_flight = False

    def on_track_gap(self) -> None:
        self._last_call_at = None
        self._locked = False

    def set_locked(self, locked: bool) -> None:
        self._locked = locked

    @property
    def in_flight(self) -> bool:
        return self._in_flight

    def should_call(self, now: float) -> bool:
        if self._in_flight:
            return False
        if self._last_call_at is None:
            return True
        interval = self._config.resync_interval_sec if self._locked else self._config.min_interval_sec
        return (now - self._last_call_at) >= interval

    def mark_call_started(self, now: float) -> None:
        self._in_flight = True
        self._last_call_at = now

    def mark_call_finished(self) -> None:
        self._in_flight = False
