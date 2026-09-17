import asyncio
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vinylyrics.recognition.shazam import ShazamIORecognizer


@pytest.mark.network
def test_recognize_identifies_a_real_track():
    path = Path("/home/dakur/Downloads/songs/Bonito.mp3")
    info = sf.info(path)
    sr = info.samplerate
    audio, _ = sf.read(path, dtype="float32", always_2d=True, start=int(30 * sr), frames=int(12 * sr))
    mono = audio.mean(axis=1).astype(np.float32)

    recognizer = ShazamIORecognizer()
    result = asyncio.run(recognizer.recognize(mono, sr))

    assert result is not None
    assert "bonito" in result.title.lower()
    assert "jarabe" in result.artist.lower()
    assert result.offset is not None
    assert result.isrc is not None
