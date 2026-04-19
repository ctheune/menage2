import datetime

import pytest

from menage2.models.todo import Todo, TodoStatus
from menage2.models import Week, Day, Recipe, Ingredient, IngredientUsage, RecipeWeekDays, RecipeSeasons, Weekday, Month, Schedule
from menage2.views.planner import add_week, send_to_shopping_list


def _make_recipe_for_all_days(dbsession):
    """Create a recipe matching every weekday and every month so suggestions() always finds it."""
    recipe = Recipe(title="Allrounder")
    recipe.schedule = Schedule()
    dbsession.add(recipe)
    dbsession.flush()
    for wd in Weekday:
        dbsession.add(RecipeWeekDays(recipe=recipe, weekday=wd))
    for m in Month:
        dbsession.add(RecipeSeasons(recipe=recipe, month=m))
    dbsession.flush()
    return recipe


def _make_week_with_recipe(dbsession):
    ingredient = Ingredient(description="Tomaten", tags="einkaufen:obst-u-gemuese")
    ingredient2 = Ingredient(description="Salz", tags="")
    dbsession.add_all([ingredient, ingredient2])
    dbsession.flush()

    recipe = Recipe(title="Tomatensalat")
    recipe.schedule = Schedule()
    dbsession.add(recipe)
    dbsession.flush()

    usage1 = IngredientUsage(recipe=recipe, ingredient=ingredient, amount="500", unit="g")
    usage2 = IngredientUsage(recipe=recipe, ingredient=ingredient2, amount=None, unit=None)
    dbsession.add_all([usage1, usage2])

    week = Week()
    dbsession.add(week)
    dbsession.flush()

    day = Day(day=datetime.date(2026, 4, 21), week=week, dinner=recipe)
    dbsession.add(day)
    dbsession.flush()

    return week, recipe


def test_send_to_shopping_list_creates_todos(app_request, dbsession):
    week, recipe = _make_week_with_recipe(dbsession)
    app_request.matchdict = {"id": str(week.id)}
    app_request.method = "POST"

    send_to_shopping_list(app_request)
    dbsession.flush()

    todos = dbsession.query(Todo).all()
    assert len(todos) == 2

    by_text = {t.text: t for t in todos}

    tomaten = by_text["Tomaten (500 g)"]
    assert tomaten.status == TodoStatus.todo
    assert "einkaufen:obst-u-gemuese" in tomaten.tags
    assert "Tomatensalat (500 g)" in tomaten.note

    salz = by_text["Salz"]
    assert salz.status == TodoStatus.todo
    assert "Tomatensalat" in salz.note
    assert "einkaufen" in salz.tags


def test_send_to_shopping_list_aggregates_amounts_across_days(app_request, dbsession):
    ingredient = Ingredient(description="Mehl", tags="")
    dbsession.add(ingredient)

    recipe1 = Recipe(title="Kuchen")
    recipe1.schedule = Schedule()
    recipe2 = Recipe(title="Brot")
    recipe2.schedule = Schedule()
    dbsession.add_all([recipe1, recipe2])
    dbsession.flush()

    dbsession.add(IngredientUsage(recipe=recipe1, ingredient=ingredient, amount="200", unit="g"))
    dbsession.add(IngredientUsage(recipe=recipe2, ingredient=ingredient, amount="300", unit="g"))

    week = Week()
    dbsession.add(week)
    dbsession.flush()

    dbsession.add(Day(day=datetime.date(2026, 4, 21), week=week, dinner=recipe1))
    dbsession.add(Day(day=datetime.date(2026, 4, 22), week=week, dinner=recipe2))
    dbsession.flush()

    app_request.matchdict = {"id": str(week.id)}
    send_to_shopping_list(app_request)
    dbsession.flush()

    todos = dbsession.query(Todo).all()
    assert len(todos) == 1
    todo = todos[0]
    assert todo.text == "Mehl (500 g)"
    assert "Kuchen (200 g)" in todo.note
    assert "Brot (300 g)" in todo.note


def test_send_to_shopping_list_untagged_ingredient_gets_sonstiges(app_request, dbsession):
    ingredient = Ingredient(description="Wasser", tags="")
    dbsession.add(ingredient)

    recipe = Recipe(title="Suppe")
    recipe.schedule = Schedule()
    dbsession.add(recipe)
    dbsession.flush()

    dbsession.add(IngredientUsage(recipe=recipe, ingredient=ingredient, amount="1", unit="l"))

    week = Week()
    dbsession.add(week)
    dbsession.flush()
    dbsession.add(Day(day=datetime.date(2026, 4, 21), week=week, dinner=recipe))
    dbsession.flush()

    app_request.matchdict = {"id": str(week.id)}
    send_to_shopping_list(app_request)
    dbsession.flush()

    todos = dbsession.query(Todo).all()
    assert len(todos) == 1
    assert "einkaufen" in todos[0].tags


def test_send_to_shopping_list_redirects_to_todos(app_request, dbsession):
    week = Week()
    dbsession.add(week)
    dbsession.flush()

    day = Day(day=datetime.date(2026, 4, 21), week=week)
    dbsession.add(day)
    dbsession.flush()

    app_request.matchdict = {"id": str(week.id)}
    response = send_to_shopping_list(app_request)
    assert response.status_int == 303
    assert "/todos" in response.location


def test_send_to_shopping_list_htmx_uses_hx_redirect(app_request, dbsession):
    week = Week()
    dbsession.add(week)
    dbsession.flush()
    dbsession.add(Day(day=datetime.date(2026, 4, 21), week=week))
    dbsession.flush()

    app_request.matchdict = {"id": str(week.id)}
    app_request.headers["HX-Request"] = "true"
    response = send_to_shopping_list(app_request)
    assert "HX-Redirect" in response.headers
    assert "/todos" in response.headers["HX-Redirect"]
    assert response.status_int == 200


def test_add_week_with_no_existing_days(app_request, dbsession):
    _make_recipe_for_all_days(dbsession)
    response = add_week(app_request)
    assert response.status_int == 303
    weeks = dbsession.query(Week).all()
    assert len(weeks) == 1
    assert len(weeks[0].days) == 7


def test_add_week_starts_after_existing_days(app_request, dbsession):
    _make_recipe_for_all_days(dbsession)

    # create a pre-existing week ending in the future
    existing_week = Week()
    dbsession.add(existing_week)
    dbsession.flush()
    future_day = datetime.date.today() + datetime.timedelta(days=10)
    dbsession.add(Day(day=future_day, week=existing_week))
    dbsession.flush()

    add_week(app_request)
    dbsession.flush()

    all_days = dbsession.query(Day).order_by(Day.day).all()
    new_days = [d for d in all_days if d.week_id != existing_week.id]
    assert new_days[0].day > future_day
