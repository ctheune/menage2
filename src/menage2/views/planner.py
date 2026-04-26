from pyramid.view import view_config
from pyramid.httpexceptions import HTTPSeeOther
from sqlalchemy.orm import joinedload
import datetime


from .. import models


@view_config(route_name="list_weeks", renderer="menage2:templates/list_weeks.pt")
def list_weeks(request):
    weeks = (
        request.dbsession.query(models.Week).options(joinedload(models.Week.days)).all()
    )
    weeks.sort(key=lambda w: w.days[0].day, reverse=True)
    return {"weeks": weeks}


@view_config(
    route_name="edit_week",
    renderer="menage2:templates/planner.pt",
    request_method="GET",
)
def edit_week_get(request):
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
    newest = newest.day if newest else datetime.date.min
    start = datetime.date.today()
    start = max([newest, start])

    for i in range(7):
        day = models.Day(day=start + datetime.timedelta(days=i + 1), week=week)
        request.dbsession.add(day)
        suggestions = day.suggestions(1)
        day.dinner = suggestions[0] if suggestions else None

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


@view_config(route_name="toggle_day_shopping", request_method="POST")
def toggle_day_shopping(request):
    day_date = datetime.datetime.strptime(request.matchdict["day"], "%Y-%m-%d").date()
    day = request.dbsession.query(models.Day).filter(models.Day.day == day_date).one()
    day.exclude_from_shopping = not day.exclude_from_shopping
    return HTTPSeeOther(request.route_url("edit_week", id=day.week.id))


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


@view_config(route_name="send_to_shopping_list", request_method="POST")
def send_to_shopping_list(request):
    from menage2.models.todo import Todo, TodoStatus

    week = (
        request.dbsession.query(models.Week)
        .options(joinedload(models.Week.days))
        .filter(models.Week.id == request.matchdict["id"])
        .one()
    )

    # aggregated: ingredient -> {unit -> {recipe_title -> amount_float}}
    aggregated = {}
    non_numeric = []

    for day in week.days:
        if not day.dinner or day.exclude_from_shopping:
            continue
        recipe_title = day.dinner.title
        for usage in day.dinner.ingredients:
            amount = usage.numeric_amount()
            if not amount:
                non_numeric.append((usage, recipe_title))
                continue
            unit = usage.unit or ""
            by_unit = aggregated.setdefault(usage.ingredient, {})
            by_recipe = by_unit.setdefault(unit, {})
            by_recipe[recipe_title] = by_recipe.get(recipe_title, 0.0) + amount

    def _fmt_amt(amount, unit):
        v = int(amount) if amount == int(amount) else amount
        return " ".join(filter(None, [str(v), unit]))

    now = datetime.datetime.now(datetime.timezone.utc)

    def _einkaufen_tags(ingredient):
        tags = {t.rstrip(":") for t in ingredient.tags_set if t.startswith("einkaufen:")}
        tags.discard("einkaufen")  # bare prefix is not a useful tag
        # Keep only the most specific tags (drop prefixes of other tags in the set)
        tags = {t for t in tags if not any(other.startswith(t + ":") for other in tags)}
        return tags or {"einkaufen:supermarkt"}

    for ingredient, by_unit in aggregated.items():
        for unit, by_recipe in by_unit.items():
            tags = _einkaufen_tags(ingredient)
            total = sum(by_recipe.values())
            total_str = _fmt_amt(total, unit)
            text = ingredient.description
            if total_str:
                text += f" ({total_str})"
            if len(by_recipe) == 1:
                parts = list(by_recipe.keys())
            else:
                parts = [f"{title} ({_fmt_amt(amt, unit)})" for title, amt in by_recipe.items()]
            note = "für: " + ", ".join(parts)
            request.dbsession.add(
                Todo(text=text, tags=tags, status=TodoStatus.todo, created_at=now, note=note)
            )

    for usage, recipe_title in non_numeric:
        tags = _einkaufen_tags(usage.ingredient)
        amt_str = _fmt_amt(usage.numeric_amount() or 0, usage.unit or "") if usage.numeric_amount() else ""
        note = "für: " + recipe_title + (f" ({amt_str})" if amt_str else "")
        request.dbsession.add(
            Todo(text=usage.to_shopping_list(), tags=tags, status=TodoStatus.todo, created_at=now, note=note)
        )

    todos_url = request.route_url("list_todos")
    if request.headers.get("HX-Request"):
        response = request.response
        response.headers["HX-Redirect"] = todos_url
        return response
    return HTTPSeeOther(todos_url)
