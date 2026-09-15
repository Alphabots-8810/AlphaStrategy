# Alliance reef fill (REEFSCAPE 2025, blue side)

Model: `src/frcsim/reefscape2025/routing.py` (WPILib 2025 AprilTag geometry, shortest paths around the reef, one trapezoidal velocity profile per leg, one robot at a time per coral station, per reef face and at the processor). Three identical robots start at faces CD / AB / KL with an empty reef (no AUTO); the task is to fill all 36 L2–L4 branches.

- **user (v 4, a 5, intake 1.0, L2/L3 0.7, L4 1.0)**: given by the user. Algae removal 0.8 s, processor / net 0.5 s and robot half-length 0.45 m are placeholders.
- **slower (intake 1.5, L2/L3 1.0, L4 1.3, algae 1.2, +0.4 s per stop)**: a pessimistic variant.
- Monte Carlo (MC): service times lognormal CV 0.25, driving CV 0.08, 3% of placements miss and are redone. Run k uses the same draws for every plan (common random numbers).
- Staged algae (rules.ALGAE_BLOCKING['B']): high on AB/EF/IJ blocks L3 of its face; low on CD/GH/KL blocks L2 and L3. A robot removes it when it first targets a blocked level.

## 1. Geometry: shortest path from a branch to the nearest coral station

| face | tag | staged algae | blocks | nearest station | path (m), near / far branch | one-way time (s) |
|---|---|---|---|---|---|---|
| KL | 19 | low | L2+L3 | 13 | 3.26 / 3.40 | 1.62 / 1.65 |
| CD | 17 | low | L2+L3 | 12 | 3.26 / 3.40 | 1.62 / 1.65 |
| AB | 18 | high | L3 | 12/13 | 3.53 / 3.53 | 1.68 / 1.68 |
| IJ | 20 | high | L3 | 13 | 4.28 / 4.61 | 1.87 / 1.95 |
| EF | 22 | high | L3 | 12 | 4.28 / 4.61 | 1.87 / 1.95 |
| GH | 21 | low | L2+L3 | 12/13 | 5.76 / 5.76 | 2.24 / 2.24 |

## 2. How many robots does it take (deterministic)

| params | robots | lower bound (s) | reactive greedy (s) |
|---|---|---|---|
| user | 1 | 201.1 | 201.8 |
| user | 2 | 100.3 | 102.4 |
| user | 3 | 66.6 | 71.4 |
| slower | 1 | 261.1 | 261.8 |
| slower | 2 | 130.3 | 134.6 |
| slower | 3 | 86.6 | 91.7 |

## 3. Does the plan matter? (3 robots, algae knocked to the floor)

| params | plan | deterministic (s) | MC mean (s) | MC p90 (s) |
|---|---|---|---|---|
| user | lower bound | 66.6 | | |
| user | annealed fixed plan (best of 4 × 15000 iters) | 67.7 | 72.9 | 76.6 |
| user | reactive greedy (soonest finish) | 71.4 | 72.9 | 76.6 |
| user | zones CD+EF / AB+GH / IJ+KL, soonest finish | 71.3 | 72.6 | 76.0 |
| user | zones CD+EF / AB+GH / IJ+KL, L4 → L3 → L2 | 71.1 | 72.5 | 75.8 |
| user | naive: own station (12/13/12), AB→KL, L4 first | 73.5 | 77.3 | 81.1 |
| user | naive: everyone uses station 12 | 74.0 | 77.9 | 81.8 |
| slower | lower bound | 86.6 | | |
| slower | annealed fixed plan (best of 4 × 15000 iters) | 88.4 | 95.1 | 100.4 |
| slower | reactive greedy (soonest finish) | 91.7 | 95.5 | 100.4 |
| slower | zones CD+EF / AB+GH / IJ+KL, soonest finish | 92.5 | 95.1 | 99.8 |
| slower | zones CD+EF / AB+GH / IJ+KL, L4 → L3 → L2 | 92.0 | 95.0 | 99.8 |
| slower | naive: own station (12/13/12), AB→KL, L4 first | 95.5 | 100.4 | 105.6 |
| slower | naive: everyone uses station 12 | 96.2 | 102.3 | 108.1 |

## 4. Every way to give each robot two faces (15 pairings; each with its best robot-to-pair assignment; MC 300 runs; soonest finish within the zone)

**user (v 4, a 5, intake 1.0, L2/L3 0.7, L4 1.0)**

| zones (robots start at CD / AB / KL) | deterministic (s) | MC mean (s) | MC p90 (s) |
|---|---|---|---|
| IJ+KL / EF+GH / AB+CD | 68.8 | 72.5 | 75.8 |
| CD+EF / AB+IJ / GH+KL | 69.9 | 72.5 | 75.9 |
| IJ+KL / CD+EF / AB+GH | 70.7 | 72.6 | 75.9 |
| AB+KL / GH+IJ / CD+EF | 69.1 | 72.7 | 76.2 |
| CD+IJ / EF+GH / AB+KL | 68.8 | 72.8 | 75.9 |
| CD+GH / AB+EF / IJ+KL | 70.3 | 72.9 | 76.3 |
| EF+IJ / GH+KL / AB+CD | 70.3 | 73.0 | 76.5 |
| AB+CD / EF+KL / GH+IJ | 68.8 | 73.0 | 76.8 |
| EF+GH / AB+IJ / CD+KL | 69.6 | 73.1 | 76.2 |
| CD+GH / AB+KL / EF+IJ | 70.7 | 73.1 | 76.9 |
| CD+IJ / AB+EF / GH+KL | 69.2 | 73.2 | 76.6 |
| AB+GH / CD+IJ / EF+KL | 70.2 | 73.3 | 76.6 |
| CD+KL / AB+EF / GH+IJ | 69.2 | 73.3 | 76.5 |
| AB+IJ / EF+KL / CD+GH | 70.4 | 73.4 | 76.5 |
| CD+KL / EF+IJ / AB+GH | 70.1 | 73.5 | 77.2 |

**slower (intake 1.5, L2/L3 1.0, L4 1.3, algae 1.2, +0.4 s per stop)**

| zones (robots start at CD / AB / KL) | deterministic (s) | MC mean (s) | MC p90 (s) |
|---|---|---|---|
| GH+KL / CD+EF / AB+IJ | 91.0 | 94.9 | 100.0 |
| IJ+KL / CD+EF / AB+GH | 91.4 | 95.4 | 100.5 |
| AB+EF / CD+GH / IJ+KL | 91.7 | 95.5 | 99.9 |
| EF+GH / IJ+KL / AB+CD | 92.1 | 95.5 | 100.1 |
| AB+KL / GH+IJ / CD+EF | 91.9 | 95.6 | 100.4 |
| AB+IJ / EF+KL / CD+GH | 89.8 | 95.6 | 100.3 |
| CD+IJ / EF+GH / AB+KL | 90.4 | 95.6 | 99.9 |
| AB+CD / EF+KL / GH+IJ | 90.4 | 95.8 | 100.7 |
| EF+IJ / CD+GH / AB+KL | 91.7 | 95.9 | 101.0 |
| AB+GH / CD+IJ / EF+KL | 91.3 | 96.0 | 100.9 |
| EF+GH / AB+IJ / CD+KL | 92.1 | 96.2 | 100.6 |
| CD+KL / AB+EF / GH+IJ | 92.8 | 96.3 | 100.5 |
| CD+IJ / AB+EF / GH+KL | 92.5 | 96.4 | 100.5 |
| GH+KL / AB+CD / EF+IJ | 91.7 | 96.4 | 101.4 |
| CD+KL / EF+IJ / AB+GH | 92.8 | 96.8 | 101.6 |

## 5. Order within the zones (CD+EF / AB+GH / IJ+KL): time to fill and coral points banked

| params | algae | order | deterministic (s) | MC mean (s) | MC p90 (s) | coral points by (20, 30, 40, 50, 60) s, deterministic run |
|---|---|---|---|---|---|---|
| user | floor | soonest finish | 71.3 | 72.6 | 76.0 | [37, 62, 82, 106, 125] |
| user | floor | L4 → L3 → L2 | 71.1 | 72.5 | 75.8 | [45, 68, 92, 114, 126] |
| user | proc_cdef | soonest finish | 76.0 | 77.8 | 81.2 | [37, 62, 82, 100, 117] |
| user | proc_cdef | L4 → L3 → L2 | 76.0 | 77.7 | 81.3 | [45, 68, 84, 100, 117] |
| slower | floor | soonest finish | 92.5 | 95.1 | 99.8 | [22, 48, 63, 78, 96] |
| slower | floor | L4 → L3 → L2 | 92.0 | 95.0 | 99.8 | [30, 55, 72, 84, 104] |
| slower | proc_cdef | soonest finish | 98.2 | 100.7 | 105.1 | [22, 48, 63, 78, 92] |
| slower | proc_cdef | L4 → L3 → L2 | 98.1 | 100.7 | 105.3 | [30, 55, 72, 80, 96] |

## 6. What to do with the staged algae (zones CD+EF / AB+GH / IJ+KL, L4 → L3 → L2)

Processor 6 points, net 4. An algae through our processor goes to the opponent's human player, who can throw it into their net for 4. In qualification matches, 2 processed algae per alliance (both alliances) is Coopertition, which cuts the Coral RP to 3 levels.

| params | policy | deterministic (s) | MC mean (s) | MC p90 (s) | processor / net / floor (deterministic run) | our algae points | opponent HP can get back |
|---|---|---|---|---|---|---|---|
| user | knock to the floor | 71.1 | 72.5 | 75.8 | 0 / 0 / 6 | 0 | ≤ 0 |
| user | CD and EF algae -> processor, the other 4 -> net | 76.0 | 77.7 | 81.3 | 2 / 4 / 0 | 28 | ≤ 8 |
| user | first 2 removed -> processor, the rest -> net | 76.6 | 78.4 | 82.1 | 2 / 4 / 0 | 28 | ≤ 8 |
| user | first 2 removed -> processor, the rest -> floor | 71.8 | 74.6 | 77.8 | 2 / 0 / 4 | 12 | ≤ 8 |
| user | all 6 -> processor | 75.8 | 78.0 | 81.8 | 6 / 0 / 0 | 36 | ≤ 24 |
| user | all 6 -> net | 76.6 | 78.8 | 82.5 | 0 / 6 / 0 | 24 | ≤ 0 |
| slower | knock to the floor | 92.0 | 95.0 | 99.8 | 0 / 0 / 6 | 0 | ≤ 0 |
| slower | CD and EF algae -> processor, the other 4 -> net | 98.1 | 100.7 | 105.3 | 2 / 4 / 0 | 28 | ≤ 8 |
| slower | first 2 removed -> processor, the rest -> net | 98.1 | 101.6 | 106.4 | 2 / 4 / 0 | 28 | ≤ 8 |
| slower | first 2 removed -> processor, the rest -> floor | 93.6 | 97.4 | 102.4 | 2 / 0 / 4 | 12 | ≤ 8 |
| slower | all 6 -> processor | 97.6 | 101.4 | 106.1 | 6 / 0 / 0 | 36 | ≤ 24 |
| slower | all 6 -> net | 98.1 | 101.9 | 106.6 | 0 / 6 / 0 | 24 | ≤ 0 |

## 7. Intake spot along the coral station (the opening is 1.93 m wide, manual 5.6.2)

| params | intake spot | lower bound (s) | reactive greedy (s) | annealed, 3000 iters (s) |
|---|---|---|---|---|
| user | station centre | 66.6 | 71.4 | 68.6 |
| user | centre or ±0.5 m | 65.8 | 68.4 | 67.2 |
| slower | station centre | 86.6 | 91.7 | 89.3 |
| slower | centre or ±0.5 m | 85.8 | 92.4 | 88.8 |

## 8. Sensitivity (user params, reactive greedy, algae to the floor, deterministic)

| change | 3 robots (s) | lower bound, 3 robots (s) | 2 robots (s) |
|---|---|---|---|
| algae removal 0.5 s | 70.5 | 66.0 | 101.9 |
| algae removal 0.8 s | 71.4 | 66.6 | 102.4 |
| algae removal 1.5 s | 71.5 | 68.0 | 105.7 |
| v 3.0 m/s, a 3.0 m/s² | 85.5 | 79.5 | 121.4 |
| v 4.0 m/s, a 5.0 m/s² | 71.4 | 66.6 | 102.4 |
| v 4.5 m/s, a 8.0 m/s² | 61.7 | 58.2 | 89.3 |

Extra seconds per stop (alignment / settling, once at the station and once at the reef). Cycle = a robot's time from the start to its last placement ÷ the coral it placed, averaged over the robots; queueing is included, so it is what you can time from match video.

| extra per stop | 3 robots: fill (s) | 3 robots: cycle (s) | 2 robots: fill (s) | 2 robots: cycle (s) |
|---|---|---|---|---|
| +0.0 s | 71.4 | 5.67 | 102.4 | 5.61 |
| +0.5 s | 83.3 | 6.68 | 120.9 | 6.62 |
| +1.0 s | 96.3 | 7.75 | 139.4 | 7.64 |
| +1.5 s | 109.3 | 8.81 | 157.9 | 8.65 |
| +2.0 s | 122.3 | 9.88 | 176.4 | 9.66 |
| +2.5 s | 135.3 | 10.93 | 194.9 | 10.68 |
| +3.0 s | 148.4 | 11.99 | 213.4 | 11.69 |

## 9. Recommended tactic: zones CD+EF / AB+GH / IJ+KL, L4 → L3 → L2, CD and EF algae -> processor, the other 4 -> net

| params | deterministic (s) | MC mean | p10 | p50 | p90 | p99 | max (MC 1000 runs) |
|---|---|---|---|---|---|---|---|
| user | 76.0 | 77.7 | 75.1 | 77.2 | 81.3 | 84.9 | 88.3 |
| slower | 98.1 | 100.6 | 96.7 | 100.2 | 105.3 | 109.9 | 114.3 |

Trips (user params, deterministic; time = placement done; * = removed that face's algae first):

- Robot 1 (CD+EF): 5 s st12→CD-L4, 11 s st12→CD-L4, 16 s st12→EF-L4, 22 s st12→EF-L4, 28 s st12→CD-L3* (algae → processor), 35 s st12→CD-L3, 41 s st12→EF-L3* (algae → processor), 49 s st12→EF-L3, 54 s st12→CD-L2, 59 s st12→CD-L2, 65 s st12→EF-L2, 70 s st12→EF-L2, 76 s st12→GH-L2
- Robot 2 (AB+GH): 6 s st12→AB-L4, 12 s st13→AB-L4, 18 s st13→GH-L4, 24 s st13→GH-L4, 31 s st12→AB-L3* (algae → net), 39 s st13→AB-L3, 46 s st13→GH-L3* (algae → net), 54 s st13→GH-L3, 60 s st12→AB-L2, 66 s st13→AB-L2, 72 s st13→GH-L2
- Robot 3 (IJ+KL): 5 s st13→KL-L4, 10 s st13→KL-L4, 16 s st13→IJ-L4, 22 s st13→IJ-L4, 28 s st13→KL-L3* (algae → net), 36 s st13→KL-L3, 42 s st13→IJ-L3* (algae → net), 50 s st13→IJ-L3, 55 s st13→KL-L2, 60 s st13→KL-L2, 65 s st13→IJ-L2, 71 s st13→IJ-L2

![route map](route_alliance.svg)

## 10. After the fill (user params): one-way leg times (s)

| from | to net shot | to processor | to nearest station |
|---|---|---|---|
| face AB (nearer branch) | 2.09 | 1.94 | 1.68 |
| face KL (nearer branch) | 1.72 | 2.31 | 1.62 |
| face IJ (nearer branch) | 1.41 | 2.03 | 1.87 |
| face GH (nearer branch) | 1.45 | 1.66 | 2.24 |
| face EF (nearer branch) | 1.78 | 1.44 | 1.87 |
| face CD (nearer branch) | 2.15 | 1.58 | 1.62 |
| coral-mark algae 1 (y = 2.20 m) | 2.76 | 2.07 | 0.97 |
| coral-mark algae 2 (y = 4.03 m) | 2.47 | 2.29 | 1.55 |
| coral-mark algae 3 (y = 5.85 m) | 2.38 | 2.61 | 0.97 |

An L1 trip (station → reef → station, average over faces): 3.67 s driving + 1.0 s intake + placement.
