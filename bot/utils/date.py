import jdatetime


def to_persian_date(gregorian_date: str, include_time: bool = False) -> str:
    try:
        if "T" in gregorian_date:
            date_part, time_part = gregorian_date.split("T")
            year, month, day = map(int, date_part.split("-"))
            persian = jdatetime.date.from_gregorian(year=year, month=month, day=day)
            if include_time and time_part:
                time_str = time_part[:8]
                return f"{persian.year}/{persian.month:02d}/{persian.day:02d} {time_str}"
            return f"{persian.year}/{persian.month:02d}/{persian.day:02d}"
        else:
            year, month, day = map(int, gregorian_date.split("-"))
            persian = jdatetime.date.from_gregorian(year=year, month=month, day=day)
            return f"{persian.year}/{persian.month:02d}/{persian.day:02d}"
    except Exception:
        return gregorian_date


def days_until_persian(gregorian_date: str) -> int:
    try:
        date_part = gregorian_date[:10]
        year, month, day = map(int, date_part.split("-"))
        persian_target = jdatetime.date.from_gregorian(year=year, month=month, day=day)
        today = jdatetime.date.today()
        return (persian_target - today).days
    except Exception:
        return 0
