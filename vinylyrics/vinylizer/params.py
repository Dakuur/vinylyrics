from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpeedParams:
    constant_offset_pct: float
    wow_freq_min_hz: float
    wow_freq_max_hz: float
    wow_depth_pct: float
    flutter_freq_min_hz: float
    flutter_freq_max_hz: float
    flutter_depth_pct: float


@dataclass(frozen=True)
class NoiseParams:
    surface_dbfs: float
    click_density_per_sec: float
    click_duration_ms: float
    click_amplitude: float
    rumble_enabled: bool
    rumble_dbfs: float
    rumble_cutoff_hz: float


@dataclass(frozen=True)
class StructureParams:
    lead_in_sec: float
    gap_sec: float
    lead_out_sec: float


@dataclass(frozen=True)
class FilterParams:
    shelf_cutoff_hz: float
    shelf_gain_db: float


@dataclass(frozen=True)
class OutputParams:
    sample_rate: int


@dataclass(frozen=True)
class VinylizerParams:
    speed: SpeedParams
    noise: NoiseParams
    structure: StructureParams
    filter: FilterParams
    output: OutputParams


DEFAULT_PARAMS_PATH = Path(__file__).parent / "default_params.toml"


def load_params(path: "Path | None" = None) -> VinylizerParams:
    toml_path = path or DEFAULT_PARAMS_PATH
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return VinylizerParams(
        speed=SpeedParams(**data["speed"]),
        noise=NoiseParams(**data["noise"]),
        structure=StructureParams(**data["structure"]),
        filter=FilterParams(**data["filter"]),
        output=OutputParams(**data["output"]),
    )
