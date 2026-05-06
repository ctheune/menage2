from datetime import datetime, timedelta

import arrow
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.view import view_config

from .dashboard import _check_dashboard_token


@view_config(
    route_name="letscook",
    renderer="menage2:templates/letscook.pt",
    permission=NO_PERMISSION_REQUIRED,
)
def letscook(request):
    _check_dashboard_token(request)
    return {}


class Timer:
    name: str

    started: datetime | None
    duration: timedelta

    def __init__(self, id, name, duration):
        self.id = id
        self.name = name
        self.duration = self.initial_duration = duration
        self.started = None

    def start(self):
        if self.started:
            return
        self.started = arrow.utcnow()

    def restart(self):
        self.started = None
        self.duration = self.initial_duration
        self.start()

    def pause(self):
        self.duration = self.remaining
        self.started = None

    @property
    def alarming(self):
        return self.started and not self.remaining

    @property
    def remaining(self):
        if self.started:
            return max([(self.started + self.duration) - arrow.utcnow(), timedelta(0)])
        return self.duration


templates = [
    {"name": "Kaffee", "duration": timedelta(minutes=2)},
    {"name": "Kaffee (koffeinfrei)", "duration": timedelta(minutes=1, seconds=30)},
    {"name": "Sandwich", "duration": timedelta(minutes=4)},
    {"name": "Eier, weich (XL)", "duration": timedelta(minutes=7)},
    {"name": "Eier, weich (L)", "duration": timedelta(minutes=6, seconds=30)},
    {"name": "Eier, weich (M)", "duration": timedelta(minutes=5, seconds=30)},
]

timerdb: dict[int, Timer] = {}


@view_config(
    route_name="timers",
    renderer="menage2:templates/timers.pt",
    permission=NO_PERMISSION_REQUIRED,
)
def timers(request):
    _check_dashboard_token(request)
    return {"timers": timerdb.values(), "templates": templates}


@view_config(
    route_name="timer",
    request_method="POST",
    renderer="string",
    permission=NO_PERMISSION_REQUIRED,
)
def start_timer(request):
    _check_dashboard_token(request)
    timer = timerdb[int(request.matchdict["id"])]
    timer.start()
    return ""


@view_config(
    route_name="timer",
    request_method="PUT",
    renderer="string",
    permission=NO_PERMISSION_REQUIRED,
)
def restart_timer(request):
    _check_dashboard_token(request)
    timerdb[int(request.matchdict["id"])].restart()
    return ""


@view_config(
    route_name="timer",
    request_method="PATCH",
    renderer="string",
    permission=NO_PERMISSION_REQUIRED,
)
def append_timer(request):
    _check_dashboard_token(request)
    timer = timerdb[int(request.matchdict["id"])]
    timer.duration += timedelta(seconds=int(request.params.get("duration")))
    return ""


@view_config(
    route_name="timer",
    request_method="DELETE",
    renderer="string",
    permission=NO_PERMISSION_REQUIRED,
)
def clear_timer(request):
    _check_dashboard_token(request)

    del timerdb[int(request.matchdict["id"])]
    return ""


@view_config(
    route_name="timer_pause",
    request_method="POST",
    renderer="string",
    permission=NO_PERMISSION_REQUIRED,
)
def pause_timer(request):
    _check_dashboard_token(request)
    timer = timerdb[int(request.matchdict["id"])]
    timer.pause()
    return ""


@view_config(
    route_name="timers",
    request_method="PUT",
    renderer="string",
    permission=NO_PERMISSION_REQUIRED,
)
def add_timer(request):
    _check_dashboard_token(request)

    name = request.params.get("name")
    duration = int(request.params.get("duration"))
    id = max([0] + list(timerdb)) + 1
    timer = Timer(id, name, timedelta(seconds=duration))
    timerdb[id] = timer
    timer.start()
    return ""
