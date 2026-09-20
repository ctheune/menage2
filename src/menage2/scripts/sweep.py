"""Create whatever the recurrence rules say should exist by now.

Completing an item already spawns its successor, so this is the catch-up:
rules nobody has touched, `every` rules whose date has come round with the
last instance still open, anything missed while the app was down.

It used to run from whichever request arrived first, which meant several
requests sweeping at once and each adding its own copy. One command on a
schedule is one sweeper. Run it every 15 minutes:

    */15 * * * *  menage2_sweep /path/to/production.ini

Idempotent, so a missed run costs nothing but lateness, and two overlapping
runs cannot both spawn the same item.
"""

import argparse
import datetime
import sys

from pyramid.paster import bootstrap, setup_logging

from ..recurrence import run_sweep


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "config_uri",
        help="Configuration file, e.g., production.ini",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Say nothing when there was nothing to do.",
    )
    return parser.parse_args(argv[1:])


def main(argv=sys.argv):
    args = parse_args(argv)
    setup_logging(args.config_uri)
    env = bootstrap(args.config_uri)

    try:
        with env["request"].tm:
            spawned = run_sweep(
                env["request"].dbsession,
                datetime.date.today(),
                datetime.datetime.now(datetime.timezone.utc),
            )
    finally:
        env["closer"]()

    if spawned or not args.quiet:
        print(f"Spawned {spawned}.")
    return 0
