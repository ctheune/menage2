from pyramid.interfaces import IBeforeRender
from pyramid.events import subscriber

from babel.core import Locale
from babel.support import Format
from babel.dates import get_timezone
from datetime import datetime, timedelta, timezone


def format_timedelta(td: timedelta):
    units = [
        ("hour", timedelta(seconds=60 * 60)),
        ("minute", timedelta(seconds=60)),
        ("second", timedelta(seconds=1)),
    ]
    result: list[int] = []
    for unit, unit_duration in units:
        if td > unit_duration:
            unit_count = int(td / unit_duration)
            result.append(unit_count)
            td = td - (unit_count * unit_duration)
        else:
            result.append(0)

    return ":".join(f"{d:02d}" for d in result)


def humanize_ago(dt: datetime) -> str:
    seconds = int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} min ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if seconds < 172800:
        return "yesterday"
    if seconds < 604800:
        return f"{seconds // 86400} days ago"
    if seconds < 2592000:
        w = seconds // 604800
        return f"{w} week{'s' if w != 1 else ''} ago"
    if seconds < 31536000:
        mo = seconds // 2592000
        return f"{mo} month{'s' if mo != 1 else ''} ago"
    y = seconds // 31536000
    return f"{y} year{'s' if y != 1 else ''} ago"


@subscriber(IBeforeRender)
def globals_factory(event):
    locale_name = event["request"].locale_name
    locale = Locale(locale_name)
    settings = event["request"].registry.settings
    tz_name = settings.get("menage.timezone", "Europe/Berlin")
    fmt = Format(locale, get_timezone(tz_name))
    event["format"] = fmt

    def humanize_ago_with_weekday(dt: datetime) -> str:
        weekday = fmt.date(dt, format="EEEE")
        absolute = fmt.datetime(dt, format="medium")
        return f"{weekday}, {absolute}"

    def _recurrence_label(todo) -> str:
        """Short label for the ↻ badge — empty string when no rule."""
        if not getattr(todo, "recurrence", None):
            return ""
        from menage2.dateparse import label_recurrence
        from menage2.recurrence import rule_to_spec
        return label_recurrence(rule_to_spec(todo.recurrence))

    event["format_timedelta"] = format_timedelta
    event["humanize_ago"] = humanize_ago
    event["absolute_with_weekday"] = humanize_ago_with_weekday
    event["_recurrence_label"] = _recurrence_label
