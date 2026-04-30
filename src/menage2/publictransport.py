import datetime
import logging

import arrow
import arrow.locales
import requests
from cachecontrol import CacheControl
from cachecontrol.caches.file_cache import FileCache

log = logging.getLogger(__name__)

session = requests.session()
session = CacheControl(session, cache=FileCache(".web_cache"))
# The target has a broken dual-stack config and requests doesn't do
# happy eyeballs yet
# Can be removed once either is solved
#
# https://github.com/public-transport/transport.rest/issues/23
# https://github.com/urllib3/urllib3/issues/797

requests.packages.urllib3.util.connection.HAS_IPV6 = False


arrow.locales.GermanBaseLocale.timeframes["minute"] = "1 min"
arrow.locales.GermanBaseLocale.timeframes["minutes"] = "{0} min"
arrow.locales.GermanBaseLocale.timeframes["now"] = "jetzt"

stations = {
    "robert-koch-straße": 953201,
    "kantstraße": 953141,
    "vogelweide": 953252,
    "hauptbahnhof": 8010159,
    "hauptbahnhof tram/bus": 963519,
    "bergmannstrost": 953040,
}


def get_departures(station_specs):
    departures = []
    for station, direction in station_specs:
        station = stations[station]
        direction = stations[direction]
        try:
            result = session.get(
                f"https://v6.db.transport.rest/stops/{station}/departures?results=10&bus=false&direction={direction}&duration=30"
            )
            data = result.json()
        except (
            requests.exceptions.JSONDecodeError,
            requests.exceptions.RequestException,
        ) as exc:
            log.warning("Failed to fetch departures for %s: %s", station, exc)
            continue
        except KeyError as exc:
            log.warning(
                "Unexpected response format for departures %s: %s", station, exc
            )
            continue

        for candidate in data.get("departures", []):
            when = arrow.get(candidate["when"])
            if when - arrow.now() < datetime.timedelta(minutes=3):
                continue
            departures.append(
                {
                    "when": when,
                    "whenRelative": when.humanize(locale="de"),
                    "line": candidate["line"]["name"],
                    "direction": candidate["direction"].split(",")[0],
                }
            )
    departures.sort(key=lambda d: d["when"])
    return departures[:5]


def get_journeys(station_specs):
    journeys = []
    for origin, destination in station_specs:
        origin = stations[origin]
        destination = stations[destination]
        try:
            result = session.get(
                f"https://v6.db.transport.rest/journeys?from={origin}&to={destination}&results=5&departure=in+5+minutes"
            )
            data = result.json()
        except (
            requests.exceptions.JSONDecodeError,
            requests.exceptions.RequestException,
        ) as exc:
            log.warning(
                "Failed to fetch journeys for %s to %s: %s", origin, destination, exc
            )
            continue
        except KeyError as exc:
            log.warning(
                "Unexpected response format for journeys %s to %s: %s",
                origin,
                destination,
                exc,
            )
            continue

        for candidate in data.get("journeys", []):
            when = arrow.get(candidate["legs"][0]["departure"])
            if when - arrow.now() < datetime.timedelta(minutes=3):
                continue

            lines = []
            for leg in candidate["legs"]:
                if "line" in leg:
                    lines.append(leg["line"]["name"])
                elif leg["walking"]:
                    lines.append("🚶🏻‍♀️")
            journeys.append(
                {
                    "when": when,
                    "whenRelative": when.humanize(locale="de"),
                    "lines": " → ".join(lines),
                    "arrives": arrow.get(candidate["legs"][-1]["arrival"]).format(
                        "HH:mm", locale="de"
                    ),
                }
            )
    journeys.sort(key=lambda d: d["when"])
    return journeys[:5]
