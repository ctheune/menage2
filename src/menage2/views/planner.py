import datetime
from dataclasses import dataclass, field

from pyramid.httpexceptions import HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from .. import models


@view_config(route_name="list_weeks", renderer="menage2:templates/list_weeks.pt")
def list_weeks(request):
    # The list shows every day's dinner, so they come along in one go.
    weeks = (
        request.dbsession.query(models.Week)
        .options(joinedload(models.Week.days).joinedload(models.Day.dinner))
        .all()
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
    recipes = (
        request.dbsession.query(models.Recipe)
        .filter(models.Recipe.active.is_(True))
        .order_by(models.Recipe.title)
    )
    return {"week": week, "recipes": recipes}


#: Who a generated shopping-list task is for. Configurable, because the
#: name used to be spelled into this file: renaming that team in the admin
#: would have left the generator addressing somebody who is no longer
#: there -- which is a refusal now rather than a quiet miss.
SHOPPING_ASSIGNEE = "planner.shopping_assignee"


def _shopping_assignees(dbsession) -> set[str]:
    """The principal shopping tasks go to, if it is configured and exists."""
    from menage2.models.config import ConfigItem
    from menage2.models.principal import Principal

    configured = dbsession.get(ConfigItem, SHOPPING_ASSIGNEE)
    name = (configured.value or "").strip() if configured else "haushalt"
    if not name:
        return set()
    known = dbsession.execute(
        select(Principal.name).where(Principal.name == name)
    ).scalar_one_or_none()
    return {known} if known else set()


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
        if not dinner:
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


def _fmt_number(value: float) -> str:
    return str(int(value) if value == int(value) else value)


@dataclass
class _Amount:
    """How much of one ingredient, in one unit.

    Numbers add up. Anything else ("1/2", "etwas") cannot, so it is kept as
    written beside the total rather than dropped.
    """

    unit: str
    total: float = 0
    uncounted: list[str] = field(default_factory=list)

    def add(self, usage) -> None:
        number = usage.numeric_amount()
        if number:
            self.total += number
        elif usage.amount:
            self.uncounted.append(usage.amount)

    def merge(self, other: "_Amount") -> None:
        self.total += other.total
        self.uncounted += other.uncounted

    def __str__(self) -> str:
        parts = [_fmt_number(self.total)] if self.total else []
        parts += self.uncounted
        return " + ".join(" ".join(filter(None, [p, self.unit])) for p in parts)


@view_config(route_name="send_to_shopping_list", request_method="POST")
def send_to_shopping_list(request):
    """One shopping item per ingredient and unit, whatever the recipes said.

    Three recipes that each want "Salz" with no amount are one "Salz", for
    all three. Amounts in the same unit add up; a different unit is a
    different item, because 500 g and 2 Stück do not.
    """
    from menage2.models.item import TodoStatus
    from menage2.models.todo import Todo

    week = (
        request.dbsession.query(models.Week)
        .options(joinedload(models.Week.days))
        .filter(models.Week.id == request.matchdict["id"])
        .one()
    )

    # (ingredient, unit) -> recipe title -> how much that recipe wants
    wanted: dict[tuple, dict[str, _Amount]] = {}

    for day in week.days:
        if not day.dinner or day.exclude_from_shopping:
            continue
        recipe_title = day.dinner.title
        for usage in day.dinner.ingredients:
            unit = usage.unit or ""
            by_recipe = wanted.setdefault((usage.ingredient, unit), {})
            by_recipe.setdefault(recipe_title, _Amount(unit)).add(usage)

    now = datetime.datetime.now(datetime.UTC)

    def _einkaufen_tags(ingredient):
        tags = {t.rstrip(":") for t in ingredient.tags}
        tags = {t for t in tags if t == "einkaufen" or t.startswith("einkaufen:")}
        # Keep only the most specific tags (drop prefixes of other tags in the
        # set). A bare "einkaufen" survives when it is all there is: somebody
        # said "buy it" without saying where.
        tags = {t for t in tags if not any(other.startswith(t + ":") for other in tags)}
        return tags or {"einkaufen:supermarkt"}

    for (ingredient, unit), by_recipe in wanted.items():
        total = _Amount(unit)
        for amount in by_recipe.values():
            total.merge(amount)
        text = ingredient.description
        if str(total):
            text += f" ({total})"
        # Who wants how much only matters when more than one recipe does.
        if len(by_recipe) == 1:
            parts = list(by_recipe)
        else:
            parts = [
                f"{title} ({amount})" if str(amount) else title
                for title, amount in by_recipe.items()
            ]
        request.dbsession.add(
            Todo.from_item(
                ingredient,
                text=text,
                tags=_einkaufen_tags(ingredient),
                note="für: " + ", ".join(parts),
                status=TodoStatus.todo,
                owner=request.identity,
                assignees=_shopping_assignees(request.dbsession),
                created_at=now,
            )
        )

    todos_url = request.route_url("list_todos")
    if request.headers.get("HX-Request"):
        response = request.response
        response.headers["HX-Redirect"] = todos_url
        return response
    return HTTPSeeOther(todos_url)
