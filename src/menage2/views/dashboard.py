from pyramid.view import view_config
from .. import models
import datetime
from menage2 import publictransport


@view_config(route_name="dashboard", renderer="menage2:templates/dashboard.pt")
def dashboard(request):
    return {}


@view_config(
    route_name="dashboard_recipes", renderer="menage2:templates/dashboard_recipes.pt"
)
def recipes(request):
    days = (
        request.dbsession.query(models.Day)
        .where(models.Day.day >= (datetime.date.today() - datetime.timedelta(days=3)))
        .order_by(models.Day.day.asc())
        .limit(10)
    )
    return {"days": days}


@view_config(
    route_name="dashboard_pt_departures",
    renderer="menage2:templates/dashboard_pt_departures.pt",
)
def departures(request):
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
)
def hbf(request):
    return {
        "journeys": publictransport.get_journeys(
            [
                ("robert-koch-straße", "hauptbahnhof"),
                ("vogelweide", "hauptbahnhof"),
            ]
        )
    }
