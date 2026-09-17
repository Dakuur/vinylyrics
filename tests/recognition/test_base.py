import dataclasses

import pytest

from vinylyrics.recognition.base import RecognitionResult


def test_recognition_result_is_frozen_and_has_expected_fields():
    result = RecognitionResult(
        title="t", artist="a", album=None, cover_url=None,
        offset=None, timeskew=None, frequencyskew=None, isrc=None,
    )
    assert result.title == "t"
    assert result.artist == "a"
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.title = "x"
