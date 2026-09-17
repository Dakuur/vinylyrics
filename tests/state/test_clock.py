import pytest

from vinylyrics.state.clock import ClockConfig, PlaybackClock


def test_clock_starts_unanchored():
    clock = PlaybackClock()
    assert clock.is_anchored is False
    assert clock.position(0.0) is None


def test_first_anchor_seeds_speed_from_timeskew():
    clock = PlaybackClock()
    clock.add_anchor(wall_time=100.0, position_sec=30.0, timeskew=0.005)
    assert clock.speed == pytest.approx(1.005)
    assert clock.position(105.0) == pytest.approx(30.0 + 5.0 * 1.005)


def test_accepted_anchor_never_causes_a_position_jump():
    clock = PlaybackClock()
    clock.add_anchor(wall_time=0.0, position_sec=0.0, timeskew=0.0)

    just_before = clock.position(10.0 - 1e-6)
    accepted = clock.add_anchor(wall_time=10.0, position_sec=10.3, timeskew=0.0)
    just_after = clock.position(10.0)

    assert accepted is True
    assert just_after == pytest.approx(just_before, abs=1e-4)


def test_accepted_anchor_fully_absorbed_after_the_window():
    config = ClockConfig(absorb_window_sec=4.0)
    clock = PlaybackClock(config)
    clock.add_anchor(wall_time=0.0, position_sec=0.0, timeskew=0.0)
    clock.add_anchor(wall_time=10.0, position_sec=10.3, timeskew=0.0)

    at_window_end = clock.position(10.0 + config.absorb_window_sec)
    expected = 10.3 + clock.speed * config.absorb_window_sec
    assert at_window_end == pytest.approx(expected, abs=1e-6)


def test_anchor_implying_large_jump_is_rejected():
    clock = PlaybackClock()
    clock.add_anchor(wall_time=0.0, position_sec=0.0, timeskew=0.0)

    accepted = clock.add_anchor(wall_time=10.0, position_sec=50.0, timeskew=0.0)

    assert accepted is False
    assert clock.speed == pytest.approx(1.0)


def test_speed_converges_via_regression_over_multiple_anchors():
    clock = PlaybackClock()
    true_speed = 1.008
    for t in (0.0, 10.0, 20.0, 30.0, 40.0):
        clock.add_anchor(wall_time=t, position_sec=true_speed * t, timeskew=0.0)

    assert clock.speed == pytest.approx(true_speed, abs=1e-6)


def test_speed_is_clamped_to_configured_range():
    config = ClockConfig(min_speed=0.97, max_speed=1.03)
    clock = PlaybackClock(config)
    clock.add_anchor(wall_time=0.0, position_sec=0.0, timeskew=0.5)  # absurd timeskew
    assert clock.speed == pytest.approx(1.03)


def test_clock_config_rejects_invariant_violation():
    with pytest.raises(ValueError):
        ClockConfig(absorb_window_sec=2.0, min_speed=0.97, reject_threshold_sec=3.0)


def test_anchor_wall_and_anchor_position_are_exposed_publicly():
    clock = PlaybackClock()
    assert clock.anchor_wall is None
    assert clock.anchor_position is None

    clock.add_anchor(wall_time=100.0, position_sec=30.0, timeskew=0.0)
    assert clock.anchor_wall == 100.0
    assert clock.anchor_position == 30.0
