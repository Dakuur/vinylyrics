from pathlib import Path

import pytest

from vinylyrics.vinylizer.params import VinylizerParams, load_params


def test_load_params_reads_the_bundled_default_file():
    params = load_params()
    assert isinstance(params, VinylizerParams)
    assert params.speed.constant_offset_pct == pytest.approx(0.8)
    assert params.speed.wow_freq_min_hz == pytest.approx(0.5)
    assert params.speed.wow_freq_max_hz == pytest.approx(2.0)
    assert params.noise.surface_dbfs == pytest.approx(-38.0)
    assert params.noise.rumble_enabled is False
    assert params.structure.lead_in_sec == pytest.approx(3.0)
    assert params.structure.gap_sec == pytest.approx(2.0)
    assert params.structure.lead_out_sec == pytest.approx(5.0)
    assert params.filter.shelf_cutoff_hz == pytest.approx(12000.0)
    assert params.filter.shelf_gain_db == pytest.approx(-6.0)
    assert params.output.sample_rate == 44100


def test_load_params_reads_a_custom_override_file(tmp_path: Path):
    custom = tmp_path / "custom.toml"
    custom.write_text(
        """
        [speed]
        constant_offset_pct = 1.5
        wow_freq_min_hz = 0.5
        wow_freq_max_hz = 2.0
        wow_depth_pct = 0.3
        flutter_freq_min_hz = 6.0
        flutter_freq_max_hz = 10.0
        flutter_depth_pct = 0.05

        [noise]
        surface_dbfs = -30.0
        click_density_per_sec = 1.0
        click_duration_ms = 3.0
        click_amplitude = 0.6
        rumble_enabled = true
        rumble_dbfs = -45.0
        rumble_cutoff_hz = 80.0

        [structure]
        lead_in_sec = 1.0
        gap_sec = 1.0
        lead_out_sec = 1.0

        [filter]
        shelf_cutoff_hz = 10000.0
        shelf_gain_db = -3.0

        [output]
        sample_rate = 48000
        """
    )
    params = load_params(custom)
    assert params.speed.constant_offset_pct == pytest.approx(1.5)
    assert params.noise.surface_dbfs == pytest.approx(-30.0)
    assert params.noise.rumble_enabled is True
    assert params.structure.lead_in_sec == pytest.approx(1.0)
    assert params.output.sample_rate == 48000
