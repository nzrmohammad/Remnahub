import jdatetime
from datetime import date as gregorian_date


def to_persian_date(gregorian_datetime: str | None, include_time: bool = False) -> str:
    if not gregorian_datetime:
        return "—"
    try:
        dt_str = gregorian_datetime
        if "T" in dt_str:
            date_part = dt_str.split("T")[0]
            time_part = dt_str.split("T")[1].split(".")[0].split("+")[0]
            year, month, day = map(int, date_part.split("-"))
            persian = jdatetime.date.from_gregorian(year=year, month=month, day=day)
            if include_time and time_part:
                return f"{persian.year}/{persian.month:02d}/{persian.day:02d} {time_part}"
            return f"{persian.year}/{persian.month:02d}/{persian.day:02d}"
        else:
            year, month, day = map(int, dt_str.split("-"))
            persian = jdatetime.date.from_gregorian(year=year, month=month, day=day)
            return f"{persian.year}/{persian.month:02d}/{persian.day:02d}"
    except Exception:
        return str(gregorian_datetime)


def days_until_persian(gregorian_date_str: str | None) -> int:
    if not gregorian_date_str:
        return 0
    try:
        date_part = gregorian_date_str[:10]
        year, month, day = map(int, date_part.split("-"))
        target = gregorian_date(year, month, day)
        today = gregorian_date.today()
        return (target - today).days
    except Exception:
        return 0
