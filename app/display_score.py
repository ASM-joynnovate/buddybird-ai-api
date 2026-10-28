import math


def parrot(probability: float) -> float:
    p = min(max(probability, 1e-9), 1 - 1e-9)

    return min(max(0.06674 * math.log(p / (1 - p)) + 0.5395, 0.0), 1.0)


def mimic(percentile: float) -> float:
    return min(max(47.0588 * percentile - 46.0588, 0.0), 1.0)
