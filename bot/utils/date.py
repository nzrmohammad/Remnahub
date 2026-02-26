import jdatetime
from datetime import date as gregorian_date, datetime, timezone
from datetime import datetime as dt
# ایمپورت ZoneInfo برای مدیریت منطقه زمانی (پایتون 3.9+)
from zoneinfo import ZoneInfo 

def to_persian_date(
    gregorian_datetime: str | int | float | None, include_time: bool = False
) -> str:
    if not gregorian_datetime:
        return "—"
    try:
        dt_obj = None
        
        # Handle Timestamp (int/float)
        if isinstance(gregorian_datetime, (int, float)):
            try:
                ts = int(gregorian_datetime)
                # تشخیص میلی‌ثانیه یا ثانیه
                if ts > 1e12:
                    ts = ts / 1000
                dt_obj = dt.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, OSError):
                return str(gregorian_datetime)
        
        # Handle String (ISO 8601)
        elif isinstance(gregorian_datetime, str):
            dt_str = str(gregorian_datetime).strip()
            
            if dt_str.endswith('Z'):
                dt_str = dt_str[:-1] + '+00:00'
            
            try:
                dt_obj = dt.fromisoformat(dt_str)
            except ValueError:
                try:
                    if '.' in dt_str:
                        dt_str = dt_str.split('.')[0]
                    if '+' in dt_str:
                        dt_str = dt_str.split('+')[0]
                    
                    if 'T' in dt_str:
                        date_part, time_part = dt_str.split('T')
                        dt_obj = dt.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")
                        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
                    else:
                        dt_obj = dt.strptime(dt_str, "%Y-%m-%d")
                        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
                except Exception:
                    return str(gregorian_datetime)

        if dt_obj:
            # اطمینان از اینکه تاریخ دارای منطقه زمانی است (اگر ندارد فرض بر UTC است)
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=timezone.utc)
            
            # --- تغییر کلیدی ---
            # تبدیل زمان UTC به زمان ایران (تهران)
            # این خط باعث می‌شود ساعت به درستی تنظیم شود (مثلاً +3:30 یا +4:30)
            dt_obj = dt_obj.astimezone(ZoneInfo("Asia/Tehran"))
            # -------------------

            # Convert to Persian Date
            persian = jdatetime.datetime.fromgregorian(datetime=dt_obj)
            
            if include_time:
                return f"{persian.year}/{persian.month:02d}/{persian.day:02d} {persian.hour:02d}:{persian.minute:02d}:{persian.second:02d}"
            return f"{persian.year}/{persian.month:02d}/{persian.day:02d}"

        return str(gregorian_datetime)

    except Exception as e:
        return str(gregorian_datetime)


def days_until_persian(gregorian_date_str: str | None) -> int:
    if not gregorian_date_str:
        return 0
    try:
        date_part = str(gregorian_date_str)[:10]
        year, month, day = map(int, date_part.split("-"))
        target = gregorian_date(year, month, day)
        today = gregorian_date.today()
        return (target - today).days
    except Exception:
        return 0