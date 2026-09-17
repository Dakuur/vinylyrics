from pathlib import Path

import pytest

from vinylyrics.server.cli import build_argparser, resolve_source


def test_parser_requires_either_file_or_line_in_default():
    parser = build_argparser()
    args = parser.parse_args([])
    assert args.file is None
    assert args.device is None  # defaults to line-in with default device


def test_parser_accepts_file_with_realtime_flag():
    parser = build_argparser()
    args = parser.parse_args(["--file", "song.wav", "--realtime"])
    assert args.file == "song.wav"
    assert args.realtime is True


def test_parser_accepts_device_and_profile_and_port():
    parser = build_argparser()
    args = parser.parse_args(["--device", "3", "--profile", "pi", "--port", "9000"])
    assert args.device == 3
    assert args.profile == "pi"
    assert args.port == 9000


def test_resolve_source_returns_file_source_when_file_given(tmp_path: Path):
    import numpy as np
    import soundfile as sf

    wav_path = tmp_path / "test.wav"
    sf.write(wav_path, np.zeros(1600, dtype="float32"), 16000)

    parser = build_argparser()
    args = parser.parse_args(["--file", str(wav_path)])
    source = resolve_source(args, sample_rate=16000)

    assert source.sample_rate == 16000


def test_resolve_source_returns_line_in_source_by_default():
    parser = build_argparser()
    args = parser.parse_args([])
    source = resolve_source(args, sample_rate=16000)

    from vinylyrics.audio.source import LineInSource
    assert isinstance(source, LineInSource)
