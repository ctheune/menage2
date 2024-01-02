from pyramid.view import view_config
from .. import models
import datetime


@view_config(route_name="dashboard", renderer="menage2:templates/dashboard.pt")
def dashboard(request):
    days = (
        request.dbsession.query(models.Day)
        .where(models.Day.day >= (datetime.date.today() - datetime.timedelta(days=3)))
        .order_by(models.Day.day.asc())
        .limit(10)
    )
    return {"days": days}
