import math

SPEEDS_KM_PER_DAY = {"road": 400, "air": 2500, "drone": 0}


def eta_days(distance_km: float, mode: str) -> int:
    return math.ceil(distance_km / SPEEDS_KM_PER_DAY[mode])
