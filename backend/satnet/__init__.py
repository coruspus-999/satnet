"""SatNet: satellite close-approach screening built on the SGP4 baseline.

Frame: TEME. Units: km and km/s. Time system: UTC. Gravity model: WGS-72
(baked into the TLE/SGP4 model). Geometric screening produces minimum
separations, never a probability of collision; Pc requires covariance that
SatNet does not fabricate.
"""
