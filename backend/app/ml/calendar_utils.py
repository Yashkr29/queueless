"""Holiday handling. Defaults are fixed-date Indian national holidays [Assumption: PRD §8 #7];
override per location via the `special_events` table. Dates are only used as model features."""
from datetime import date

DEFAULT_FIXED_HOLIDAYS = {(1, 1), (1, 26), (8, 15), (10, 2), (12, 25)}


def is_default_holiday(d: date) -> bool:
    return (d.month, d.day) in DEFAULT_FIXED_HOLIDAYS
