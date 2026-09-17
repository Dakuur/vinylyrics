# vinylyrics/vinylizer/build.py
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from pedalboard import HighShelfFilter, Pedalboard

from vinylyrics.vinylizer.library import TrackMeta
from vinylyrics.vinylizer.noise import build_noise_layer
from vinylyrics.vinylizer.params import VinylizerParams
from vinylyrics.vinylizer.speed import apply_speed_variation, random_speed_profile


def select_tracks(tracks: list[TrackMeta], n: int, rng: np.random.Generator) -> list[TrackMeta]:
    usable = [t for t in tracks if t.usable]
    n = min(n, len(usable))
    indices = rng.choice(len(usable), size=n, replace=False)
    return [usable[i] for i in indices]


def partition_tracks(
    tracks: list[TrackMeta], n: int, rng: np.random.Generator
) -> list[list[TrackMeta]]:
    usable = [t for t in tracks if t.usable]
    order = rng.permutation(len(usable))
    shuffled = [usable[i] for i in order]
    return [shuffled[i : i + n] for i in range(0, len(shuffled), n)]


def _load_mono(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    return audio.mean(axis=1).astype(np.float32), sr


def build_side(
    tracks: list[TrackMeta],
    params: VinylizerParams,
    rng: np.random.Generator,
    max_track_seconds: "float | None" = None,
) -> tuple[np.ndarray, dict]:
    output_sr = params.output.sample_rate
    lead_in_samples = int(params.structure.lead_in_sec * output_sr)
    gap_samples = int(params.structure.gap_sec * output_sr)
    lead_out_samples = int(params.structure.lead_out_sec * output_sr)

    processed = []
    for track in tracks:
        audio, source_sr = _load_mono(track.path)
        if max_track_seconds is not None:
            audio = audio[: int(max_track_seconds * source_sr)]
        profile = random_speed_profile(rng, params.speed)
        resampled = apply_speed_variation(audio, source_sr, output_sr, profile)
        processed.append((track, profile, resampled))

    total_samples = (
        lead_in_samples
        + sum(len(a) for _, _, a in processed)
        + gap_samples * max(0, len(processed) - 1)
        + lead_out_samples
    )

    noise_layer = build_noise_layer(total_samples, output_sr, params.noise, rng)
    music_layer = np.zeros(total_samples, dtype=np.float32)

    offset = lead_in_samples
    truth_tracks = []
    for i, (track, profile, audio) in enumerate(processed):
        music_layer[offset : offset + len(audio)] += audio
        truth_tracks.append(
            {
                "order": i,
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "source_path": str(track.path),
                "start_sec": offset / output_sr,
                "end_sec": (offset + len(audio)) / output_sr,
                "speed_offset": profile.offset,
                "wow_freq_hz": profile.wow_freq_hz,
                "wow_depth": profile.wow_depth,
                "wow_phase": profile.wow_phase,
                "flutter_freq_hz": profile.flutter_freq_hz,
                "flutter_depth": profile.flutter_depth,
                "flutter_phase": profile.flutter_phase,
            }
        )
        offset += len(audio) + gap_samples

    mixed = music_layer + noise_layer

    board = Pedalboard(
        [HighShelfFilter(cutoff_frequency_hz=params.filter.shelf_cutoff_hz, gain_db=params.filter.shelf_gain_db)]
    )
    final = board(mixed, output_sr).astype(np.float32)

    peak = float(np.max(np.abs(final))) if len(final) else 0.0
    if peak > 0.95:
        final = final * (0.95 / peak)

    truth = {
        "sample_rate": output_sr,
        "duration_sec": len(final) / output_sr,
        "tracks": truth_tracks,
    }
    return final, truth


def write_side(audio: np.ndarray, truth: dict, output_dir: Path, stem: str) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / f"{stem}.wav"
    json_path = output_dir / f"{stem}.truth.json"
    sf.write(wav_path, audio, truth["sample_rate"])
    json_path.write_text(json.dumps(truth, indent=2, ensure_ascii=False))
    return wav_path, json_path
