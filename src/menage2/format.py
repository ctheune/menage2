from pyramid.interfaces import IBeforeRender
from pyramid.events import subscriber

from babel.core import Locale
from babel.support import Format
from babel.dates import get_timezone
from datetime import timedelta


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


@subscriber(IBeforeRender)
def globals_factory(event):
    locale_name = event["request"].locale_name
    locale = Locale(locale_name)
    event["format"] = Format(locale, get_timezone("Europe/Berlin"))

    event["format_timedelta"] = format_timedelta
