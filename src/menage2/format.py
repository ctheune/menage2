from pyramid.interfaces import IBeforeRender
from pyramid.events import subscriber

from babel.core import Locale
from babel.support import Format
from babel.dates import get_timezone


@subscriber(IBeforeRender)
def globals_factory(event):
    locale_name = event["request"].locale_name
    locale = Locale(locale_name)
    event["format"] = Format(locale, get_timezone("Europe/Berlin"))
