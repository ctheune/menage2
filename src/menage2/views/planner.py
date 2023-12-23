from pyramid.view import view_config
from pyramid.httpexceptions import HTTPSeeOther
from sqlalchemy.orm import joinedload
import datetime


from .. import models


@view_config(route_name="list_weeks", renderer="menage2:templates/list_weeks.pt")
def list_weeks(request):
    weeks = request.dbsession.query(models.Week).order_by(models.Week.id.desc())
    return {"weeks": weeks}


@view_config(route_name="show_week", renderer="menage2:templates/show_week.pt")
@view_config(
    route_name="edit_week",
    renderer="menage2:templates/planner.pt",
    request_method="GET",
)
def show_week(request):
    week = (
        request.dbsession.query(models.Week)
        .filter(models.Week.id == request.matchdict["id"])
        .one()
    )
    recipes = request.dbsession.query(models.Recipe).filter(
        models.Recipe.active.is_(True)
    )
    return {"week": week, "recipes": recipes}


@view_config(
    route_name="edit_week",
    renderer="menage2:templates/planner.pt",
    request_method="POST",
)
def edit_week(request):
    week = (
        request.dbsession.query(models.Week)
        .options(joinedload(models.Week.days))
        .filter(models.Week.id == request.matchdict["id"])
        .one()
    )

    for i, dinner_freestyle in enumerate(request.params.getall("dinner_freestyle")):
        week.days[i].dinner_freestyle = dinner_freestyle

    for i, note in enumerate(request.params.getall("note")):
        week.days[i].note = note

    for i, dinner in enumerate(request.params.getall("dinner")):
        if dinner == "none":
            week.days[i].dinner_id = None
        else:
            week.days[i].dinner_id = int(dinner)

    return HTTPSeeOther(request.route_url("edit_week", id=week.id))


@view_config(route_name="add_week", request_method="PUT")
def add_week(request):
    week = models.Week()
    request.dbsession.add(week)

    newest = request.dbsession.query(models.Day).order_by(models.Day.day.desc()).first()
    newest = newest.day if newest else datetime.date.min()
    start = datetime.date.today()
    start = max([newest, start])

    for i in range(7):
        day = models.Day(day=start + datetime.timedelta(days=i + 1), week=week)
        request.dbsession.add(day)
        day.dinner = day.suggestions(1)[0]

    return HTTPSeeOther(request.route_url("edit_week", id=week.id))


@view_config(route_name="delete_day", request_method="DELETE")
def delete_day(request):
    day_date = datetime.datetime.strptime(request.matchdict["day"], "%Y-%m-%d").date()

    day = request.dbsession.query(models.Day).filter(models.Day.day == day_date).one()
    week = day.week
    week.days.remove(day)

    return HTTPSeeOther(request.route_url("edit_week", id=week.id))


@view_config(route_name="add_day", request_method="PUT")
def add_day(request):
    week = (
        request.dbsession.query(models.Week)
        .filter(models.Week.id == request.matchdict["id"])
        .one()
    )
    position = request.matchdict["position"]

    if position == "before":
        day = models.Day(day=week.first.day - datetime.timedelta(days=1), week=week)
    elif position == "after":
        day = models.Day(day=week.last.day + datetime.timedelta(days=1), week=week)
    else:
        raise ValueError(f"Invalid position {position}")
    request.dbsession.add(day)
    day.dinner = day.suggestions(1)[0]

    return HTTPSeeOther(request.route_url("edit_week", id=week.id))


@view_config(route_name="set_dinner", request_method="POST")
def set_dinner(request):
    day = (
        request.dbsession.query(models.Day)
        .filter(
            models.Day.day
            == datetime.datetime.strptime(request.matchdict["day"], "%Y-%m-%d").date()
        )
        .first()
    )

    dinner_id = request.matchdict["recipe"]
    if dinner_id == "none":
        day.dinner_id = None
    else:
        day.dinner_id = int(dinner_id)

    return HTTPSeeOther(request.route_url("edit_week", id=day.week.id))


@view_config(route_name="send_to_rtm", request_method="POST")
def send_to_rtm(request):
    week = (
        request.dbsession.query(models.Week)
        .options(joinedload(models.Week.days))
        .filter(models.Week.id == request.matchdict["id"])
        .one()
    )

    week.send_to_rtm()
