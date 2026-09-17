from vinylyrics.recognition.cadence import CadenceConfig, CallCadencePolicy


def test_allows_first_call_immediately():
    policy = CallCadencePolicy()
    assert policy.should_call(now=0.0) is True


def test_blocks_second_call_before_min_interval():
    policy = CallCadencePolicy(CadenceConfig(min_interval_sec=8.0, resync_interval_sec=45.0))
    policy.mark_call_started(now=0.0)
    policy.mark_call_finished()
    assert policy.should_call(now=5.0) is False
    assert policy.should_call(now=8.0) is True


def test_never_two_simultaneous_calls():
    policy = CallCadencePolicy()
    policy.mark_call_started(now=0.0)
    assert policy.in_flight is True
    assert policy.should_call(now=100.0) is False
    policy.mark_call_finished()
    assert policy.in_flight is False


def test_track_gap_forces_immediate_call_allowed():
    policy = CallCadencePolicy(CadenceConfig(min_interval_sec=8.0))
    policy.mark_call_started(now=0.0)
    policy.mark_call_finished()
    assert policy.should_call(now=1.0) is False
    policy.on_track_gap()
    assert policy.should_call(now=1.0) is True


def test_locked_state_uses_resync_interval():
    policy = CallCadencePolicy(CadenceConfig(min_interval_sec=8.0, resync_interval_sec=45.0))
    policy.set_locked(True)
    policy.mark_call_started(now=0.0)
    policy.mark_call_finished()
    assert policy.should_call(now=10.0) is False
    assert policy.should_call(now=45.0) is True


def test_track_gap_also_clears_locked_state():
    policy = CallCadencePolicy(CadenceConfig(min_interval_sec=8.0, resync_interval_sec=45.0))
    policy.set_locked(True)
    policy.mark_call_started(now=0.0)
    policy.mark_call_finished()

    policy.on_track_gap()
    policy.mark_call_started(now=1.0)
    policy.mark_call_finished()

    # after the gap, cadence should be back to the fast min_interval, not the slow resync interval
    assert policy.should_call(now=1.0 + 8.0) is True
    assert policy.should_call(now=1.0 + 7.0) is False
