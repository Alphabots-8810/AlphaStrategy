"""REEFSCAPE 2025 rule constants.

Primary sources (fetched 2026-09-11):
  - 2025 Game Manual, firstfrc.blob.core.windows.net/frc2025/Manual/2025GameManual.pdf
    (Section 5 V4, Section 6 V13, Section 7 V11)
  - Team Update 21 (2025-04-08) and earlier updates, TeamUpdate-Combined.pdf

Every value below cites its manual section. Anything that is a modelling
assumption rather than a rule lives in profiles.py / sim.GameConfig instead.
"""

# --- Match timing (§6.4, Table 5-1) ----------------------------------------
AUTO_S = 15.0
TELEOP_S = 135.0
FINAL_WARNING_S = 20.0  # "final 20 seconds" (G428 CAGE protection window)

# --- REEF geometry (§5.3) ---------------------------------------------------
REEF_FACES = 6
BRANCHES_PER_LEVEL = 12          # L2, L3, L4 each have 12 BRANCHES
BRANCHES_PER_FACE_PER_LEVEL = 2  # 12 branches / 6 faces
# L1 is the trough: no per-location tracking, no hard capacity (§6.5.1).

# --- Staged ALGAE (§6.3.4.2, Figure 6-3) -------------------------------------
# 6 ALGAE per REEF, each resting on a pair of BRANCHES of one face, alternating
# high/low around the reef (3 + 3). "Staged ALGAE will not contact CORAL placed
# on L4."  A CORAL touching an ALGAE is not scored (§6.5.1), so staged ALGAE
# block scoring on the branches they sit on / against.
LOW_ALGAE_PER_REEF = 3
HIGH_ALGAE_PER_REEF = 3
# §6.3.4.1 A / §6.3.4.2 B / Figure 6-2: 6 CORAL MARKS, each a CORAL with an ALGAE
# on top, "3 of each per ALLIANCE". AUTO interaction with them is not modelled;
# the sim starts TELEOP with these ALGAE in the floor pool (GameConfig.mark_algae).
CORAL_MARK_ALGAE_PER_ALLIANCE = 3

# Which levels on a face are blocked while that face's staged ALGAE remains.
# NOT stated numerically in the manual; inferred from Figure 6-3 + §6.5.1.
# Two readings, selectable via GameConfig.algae_blocking:
#   "B" (default): low ALGAE (sits on the L2 pair) blocks L2 and L3 on its face;
#                  high ALGAE (sits on the L3 pair) blocks L3 on its face.
#                  => L3 has 0 free branches at match start.
#   "A":           each ALGAE blocks only the pair it rests on
#                  (low -> L2, high -> L3). => L2 and L3 each start with 6 free.
# The manual's explicit L4-only non-contact guarantee is weak evidence for "B".
ALGAE_BLOCKING = {
    "A": {"low": (2,), "high": (3,)},
    "B": {"low": (2, 3), "high": (3,)},
}

# --- Point values (Table 6-2) ------------------------------------------------
LEAVE_PTS = 3  # AUTO only
CORAL_PTS = {
    "auto":   {1: 3, 2: 4, 3: 6, 4: 7},
    "teleop": {1: 2, 2: 3, 3: 4, 4: 5},
}
PROCESSOR_PTS = 6  # same AUTO/TELEOP
NET_PTS = 4        # same AUTO/TELEOP; also what a HUMAN PLAYER scores (§6.1)
PARK_PTS = 2
SHALLOW_CAGE_PTS = 6
DEEP_CAGE_PTS = 12
CAGE_PTS = {"shallow": SHALLOW_CAGE_PTS, "deep": DEEP_CAGE_PTS}

# --- Ranking points (Table 6-2 + Team Update 21) ------------------------------
RP_WIN = 3
RP_TIE = 1
RP_AUTO = 1      # all non-BYPASSED ROBOTS LEAVE and >=1 CORAL scored in AUTO
RP_CORAL = 1
RP_BARGE = 1
# Regular season & District Championships: 5 CORAL per level / 14 BARGE pts.
# FIRST Championship (TU21, 2025-04-08): raised to 7 / 16. The final manual PDF
# (Section 6 V13) prints the Championship values.
THRESHOLDS = {
    "regular": {"coral_per_level": 5, "barge_pts": 14},
    "champs":  {"coral_per_level": 7, "barge_pts": 16},
}
CORAL_RP_LEVELS = 4       # "at least N CORAL scored on each level"
CORAL_RP_LEVELS_COOP = 3  # with Coopertition: "on each of 3 levels"

# --- Coopertition (§6.5.3) ---------------------------------------------------
# Qualification MATCHES only: >= 2 ALGAE scored in EACH ALLIANCE's PROCESSOR.
COOP_MIN_PROCESSED_EACH = 2

# --- Possession / field limits -------------------------------------------------
MAX_CORAL_CONTROLLED = 1   # G409: 1 CORAL and 1 ALGAE simultaneously
MAX_ALGAE_CONTROLLED = 1
PROCESSOR_AREA_ALGAE_STORAGE = 4  # G435 (3 on holders + 1 on ramp)
CORAL_SUPPLY_PER_ALLIANCE = 57    # §6.3.4.1: 57-60 behind the CORAL STATIONS
CORAL_STATIONS_PER_ALLIANCE = 2   # §5.6.2 (one per corner on each alliance wall)
CAGES_PER_ALLIANCE = 3            # §5.4 (team picks shallow/deep for its own)

# --- Processor -> opponent HUMAN PLAYER flow (§5.5, §6.1) --------------------
# An ALGAE through our PROCESSOR rolls into the OPPONENT's PROCESSOR AREA; their
# HUMAN PLAYER may throw it into THEIR NET (4 pts for them). G404: no HP
# throwing in AUTO.
