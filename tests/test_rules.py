"""Regression guard on Table 6-2 / Team Update 21 constants."""
from frcsim.reefscape2025 import rules


def test_point_values_table_6_2():
    assert rules.LEAVE_PTS == 3
    assert rules.CORAL_PTS["auto"] == {1: 3, 2: 4, 3: 6, 4: 7}
    assert rules.CORAL_PTS["teleop"] == {1: 2, 2: 3, 3: 4, 4: 5}
    assert (rules.PROCESSOR_PTS, rules.NET_PTS) == (6, 4)
    assert (rules.PARK_PTS, rules.SHALLOW_CAGE_PTS, rules.DEEP_CAGE_PTS) == (2, 6, 12)


def test_rp_thresholds():
    assert rules.THRESHOLDS["regular"] == {"coral_per_level": 5, "barge_pts": 14}
    assert rules.THRESHOLDS["champs"] == {"coral_per_level": 7, "barge_pts": 16}
    assert (rules.CORAL_RP_LEVELS, rules.CORAL_RP_LEVELS_COOP) == (4, 3)
    assert rules.COOP_MIN_PROCESSED_EACH == 2
    assert (rules.RP_WIN, rules.RP_TIE) == (3, 1)


def test_timing_and_geometry():
    assert (rules.AUTO_S, rules.TELEOP_S) == (15.0, 135.0)
    assert rules.BRANCHES_PER_LEVEL == 12
    assert rules.LOW_ALGAE_PER_REEF + rules.HIGH_ALGAE_PER_REEF == 6
