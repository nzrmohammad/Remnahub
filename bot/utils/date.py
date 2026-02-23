import jdatetime
from datetime import date as gregorian_date


def to_persian_date(gregorian_datetime: str, include_time: bool = False) -> str:
    try:
        if not gregorian_datetime:
            return "—"
        if "T" in gregorian_datetime:
            date_part, time_part = gregorian_datetime.split("T")
            year, month, day = map(int, date_part.split("-"))
            persian = jdatetime.date.from_gregorian(year=year, month=month, day=day)
            if include_time and time_part:
                time_str = time_part[:8]
                return f"{persian.year}/{persian.month:02d}/{persian.day:02d} {time_str}"
            return f"{persian.year}/{persian.month:02d}/{persian.day:02d}"
        else:
            year, month, day = map(int, gregorian_datetime.split("-"))
            persian = jdatetime.date.from_gregorian(year=year, month=month, day=day)
            return f"{persian.year}/{persian.month:02d}/{persian.day:02d}"
    except Exception as e:
        return gregorian_datetime


def days_until_persian(gregorian_date_str: str) -> int:
    try:
        if not gregorian_date_str:
            return 0
        date_part = gregorian_date_str[:10]
        year, month, day = map(int, date_part.split("-"))
        target = gregorian_date(year, month, day)
        today = gregorian_date.today()
        return (target - today).days
    except Exception:
        return 0
