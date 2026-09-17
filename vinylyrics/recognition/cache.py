from __future__ import annotations

import hashlib
import json
from pathlib import Path


def hash_audio(wav_bytes: bytes) -> str:
    return hashlib.sha256(wav_bytes).hexdigest()


class DiskRecognitionCache:
    def __init__(self, cache_dir: Path):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, audio_hash: str) -> Path:
        return self._cache_dir / f"{audio_hash}.json"

    def get(self, audio_hash: str) -> "dict | None":
        path = self._path_for(audio_hash)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def set(self, audio_hash: str, response: dict) -> None:
        path = self._path_for(audio_hash)
        path.write_text(json.dumps(response))
