import numpy as np
from math import isfinite
from numbers import Real

try:
    from .schemas import Pattern
except ImportError:
    from schemas import Pattern


def calculate_user_patterns(daily_logs: list[dict]) -> list[Pattern]:
    """Calculate sleep/stress correlation from paired daily measurements."""
    pairs = []
    for log in daily_logs:
        sleep, stress = log.get("sleepHours"), log.get("stress")
        if all(isinstance(value, Real) and not isinstance(value, bool) and isfinite(value)
               for value in (sleep, stress)):
            pairs.append((sleep, stress))

    if len(pairs) < 5:
        return []
    sleep_hours, stress_scores = zip(*pairs)
    if len(set(sleep_hours)) < 2 or len(set(stress_scores)) < 2:
        return []
    correlation = float(np.corrcoef(sleep_hours, stress_scores)[0, 1])
    if not isfinite(correlation) or abs(correlation) < 0.3:
        return []
    return [Pattern(id="pat_sleep_stress_01", x="sleepHours", y="stress",
                    correlation=correlation, sampleSize=len(pairs))]