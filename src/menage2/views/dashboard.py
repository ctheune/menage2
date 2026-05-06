import datetime
import hmac

from pyramid.httpexceptions import HTTPNotFound
from pyramid.response import Response
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.view import view_config

from menage2 import publictransport

from .. import models
from ..models.config import ConfigItem
from ..views.auth import DASHBOARD_TOKEN_KEY


def _check_dashboard_token(request):
    """Return None if token is valid, or a Response (403/404) if not."""
    config_item = request.dbsession.get(ConfigItem, DASHBOARD_TOKEN_KEY)
    if config_item is None or not config_item.value:
        raise HTTPNotFound(
            "Dashboard URL not configured. Set it up in the admin panel."
        )
    expected = config_item.value.encode()
    provided = request.matchdict.get("token", "").encode()
    if not hmac.compare_digest(expected, provided):
        return Response("Invalid dashboard token.", status=403)
    return None


@view_config(
    route_name="dashboard",
    renderer="menage2:templates/dashboard.pt",
    permission=NO_PERMISSION_REQUIRED,
)
def dashboard(request):
    err = _check_dashboard_token(request)
    if err is not None:
        return err
    token = request.matchdict["token"]
    return {
        "dashboard_recipes_url": request.route_url("dashboard_recipes", token=token),
        "dashboard_pt_departures_url": request.route_url(
            "dashboard_pt_departures", token=token
        ),
        "dashboard_pt_hbf_url": request.route_url("dashboard_pt_hbf", token=token),
        "dashboard_timers_url": request.route_url("timers", token=token),
    }


@view_config(
    route_name="dashboard_recipes",
    renderer="menage2:templates/dashboard_recipes.pt",
    permission=NO_PERMISSION_REQUIRED,
)
def recipes(request):
    err = _check_dashboard_token(request)
    if err is not None:
        return err
    days = (
        request.dbsession.query(models.Day)
        .where(models.Day.day >= (datetime.date.today() - datetime.timedelta(days=1)))
        .order_by(models.Day.day.asc())
        .limit(10)
    )
    return {"days": days}


@view_config(
    route_name="dashboard_pt_departures",
    renderer="menage2:templates/dashboard_pt_departures.pt",
    permission=NO_PERMISSION_REQUIRED,
)
def departures(request):
    err = _check_dashboard_token(request)
    if err is not None:
        return err
    return {
        "departures": publictransport.get_departures(
            [
                ("robert-koch-straße", "kantstraße"),
                ("vogelweide", "bergmannstrost"),
            ]
        )
    }


@view_config(
    route_name="dashboard_pt_hbf",
    renderer="menage2:templates/dashboard_pt_hbf.pt",
    permission=NO_PERMISSION_REQUIRED,
)
def hbf(request):
    err = _check_dashboard_token(request)
    if err is not None:
        return err
    return {
        "journeys": publictransport.get_journeys(
            [
                ("robert-koch-straße", "hauptbahnhof"),
                ("vogelweide", "hauptbahnhof"),
            ]
        )
    }
