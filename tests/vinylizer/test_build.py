import json
from pathlib import Path

import numpy as np
import pytest

from vinylyrics.vinylizer.build import (
    build_side,
    partition_tracks,
    select_tracks,
    write_side,
)
from vinylyrics.vinylizer.library import TrackMeta
from vinylyrics.vinylizer.params import (
    FilterParams,
    NoiseParams,
    OutputParams,
    SpeedParams,
    StructureParams,
    VinylizerParams,
)


def _make_track(tmp_path: Path, name: str, seconds: float, sr: int = 44100, usable: bool = True) -> TrackMeta:
    import soundfile as sf

    path = tmp_path / name
    t = np.arange(int(sr * seconds))
    audio = (0.2 * np.sin(2 * np.pi * 220 * t / sr)).astype(np.float32)
    sf.write(path, audio, sr)
    missing = () if usable else ("title", "artist")
    return TrackMeta(
        path=path,
        title=None if not usable else f"Title {name}",
        artist=None if not usable else "Artist",
        album="Album",
        duration_seconds=seconds,
        missing_fields=missing,
    )


def _zero_speed_params(sample_rate: int = 44100, lead_in=0.1, gap=0.1, lead_out=0.1) -> VinylizerParams:
    return VinylizerParams(
        speed=SpeedParams(
            constant_offset_pct=0.0,
            wow_freq_min_hz=1.0,
            wow_freq_max_hz=1.0,
            wow_depth_pct=0.0,
            flutter_freq_min_hz=8.0,
            flutter_freq_max_hz=8.0,
            flutter_depth_pct=0.0,
        ),
        noise=NoiseParams(
            surface_dbfs=-38.0,
            click_density_per_sec=0.1,
            click_duration_ms=3.0,
            click_amplitude=0.3,
            rumble_enabled=False,
            rumble_dbfs=-45.0,
            rumble_cutoff_hz=80.0,
        ),
        structure=StructureParams(lead_in_sec=lead_in, gap_sec=gap, lead_out_sec=lead_out),
        filter=FilterParams(shelf_cutoff_hz=12000.0, shelf_gain_db=-6.0),
        output=OutputParams(sample_rate=sample_rate),
    )


def _default_speed_params(**kwargs) -> VinylizerParams:
    params = _zero_speed_params(**kwargs)
    return VinylizerParams(
        speed=SpeedParams(
            constant_offset_pct=0.8,
            wow_freq_min_hz=0.5,
            wow_freq_max_hz=2.0,
            wow_depth_pct=0.3,
            flutter_freq_min_hz=6.0,
            flutter_freq_max_hz=10.0,
            flutter_depth_pct=0.05,
        ),
        noise=params.noise,
        structure=params.structure,
        filter=params.filter,
        output=params.output,
    )


def test_select_tracks_picks_only_usable_and_is_seed_reproducible(tmp_path: Path):
    tracks = [
        _make_track(tmp_path, "a.wav", 1.0),
        _make_track(tmp_path, "b.wav", 1.0),
        _make_track(tmp_path, "c.wav", 1.0, usable=False),
        _make_track(tmp_path, "d.wav", 1.0),
    ]
    selected_a = select_tracks(tracks, 2, np.random.default_rng(5))
    selected_b = select_tracks(tracks, 2, np.random.default_rng(5))
    assert len(selected_a) == 2
    assert all(t.usable for t in selected_a)
    assert [t.path for t in selected_a] == [t.path for t in selected_b]


def test_select_tracks_caps_at_available_usable_count(tmp_path: Path):
    tracks = [_make_track(tmp_path, "a.wav", 1.0), _make_track(tmp_path, "b.wav", 1.0, usable=False)]
    selected = select_tracks(tracks, 5, np.random.default_rng(1))
    assert len(selected) == 1


def test_partition_tracks_covers_all_usable_tracks_exactly_once(tmp_path: Path):
    tracks = [_make_track(tmp_path, f"t{i}.wav", 1.0) for i in range(7)]
    groups = partition_tracks(tracks, 3, np.random.default_rng(2))
    assert [len(g) for g in groups] == [3, 3, 1]
    flattened = {t.path for g in groups for t in g}
    assert flattened == {t.path for t in tracks}


def test_build_side_structure_is_exact_with_zero_speed_variation(tmp_path: Path):
    track1 = _make_track(tmp_path, "one.wav", 2.0)
    track2 = _make_track(tmp_path, "two.wav", 3.0)
    params = _zero_speed_params(sample_rate=44100, lead_in=0.5, gap=0.2, lead_out=0.3)

    audio, truth = build_side([track1, track2], params, np.random.default_rng(9))

    sr = params.output.sample_rate
    expected_len = int(0.5 * sr) + int(2.0 * sr) + int(0.2 * sr) + int(3.0 * sr) + int(0.3 * sr)
    assert audio.shape[0] == pytest.approx(expected_len, abs=5)
    assert audio.dtype == np.float32

    assert len(truth["tracks"]) == 2
    assert truth["tracks"][0]["order"] == 0
    assert truth["tracks"][0]["title"] == "Title one.wav"
    assert truth["tracks"][0]["speed_offset"] == pytest.approx(1.0)
    assert truth["tracks"][0]["start_sec"] == pytest.approx(0.5, abs=0.01)
    assert truth["tracks"][0]["end_sec"] == pytest.approx(2.5, abs=0.02)
    assert truth["tracks"][1]["start_sec"] == pytest.approx(2.5 + 0.2, abs=0.02)
    assert truth["sample_rate"] == 44100


def test_build_side_applies_nonzero_speed_variation(tmp_path: Path):
    track = _make_track(tmp_path, "one.wav", 2.0)
    params = _default_speed_params(lead_in=0.1, gap=0.1, lead_out=0.1)

    _, truth = build_side([track], params, np.random.default_rng(3))

    offset = truth["tracks"][0]["speed_offset"]
    assert 1.0 - 0.008 <= offset <= 1.0 + 0.008


def test_build_side_dry_mode_truncates_tracks(tmp_path: Path):
    track = _make_track(tmp_path, "long.wav", 5.0)
    params = _zero_speed_params(lead_in=0.0, gap=0.0, lead_out=0.0)

    audio, truth = build_side([track], params, np.random.default_rng(4), max_track_seconds=2.0)

    sr = params.output.sample_rate
    assert audio.shape[0] == pytest.approx(int(2.0 * sr), abs=5)
    assert truth["tracks"][0]["end_sec"] == pytest.approx(2.0, abs=0.02)


def test_write_side_creates_wav_and_truth_json(tmp_path: Path):
    import soundfile as sf

    audio = np.zeros(44100, dtype=np.float32)
    truth = {"sample_rate": 44100, "duration_sec": 1.0, "tracks": []}

    wav_path, json_path = write_side(audio, truth, tmp_path / "out", index=1)

    assert wav_path.name == "cara_01.wav"
    assert json_path.name == "cara_01.truth.json"
    assert wav_path.exists() and json_path.exists()

    read_audio, read_sr = sf.read(wav_path)
    assert read_sr == 44100
    assert read_audio.shape[0] == pytest.approx(44100, abs=5)

    loaded_truth = json.loads(json_path.read_text())
    assert loaded_truth == truth
