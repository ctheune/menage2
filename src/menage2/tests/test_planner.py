import datetime

from menage2.models import (
    Day,
    Ingredient,
    IngredientUsage,
    Month,
    Recipe,
    RecipeSeasons,
    RecipeWeekDays,
    Schedule,
    Week,
    Weekday,
)
from menage2.models.item import TodoStatus
from menage2.models.todo import Todo
from menage2.views.planner import add_week, send_to_shopping_list, toggle_day_shopping


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
    ingredient = Ingredient(
        description="Tomaten", tags={"einkaufen:supermarkt:obst-u-gemuese"}
    )
    ingredient2 = Ingredient(description="Salz", tags=set())
    dbsession.add_all([ingredient, ingredient2])
    dbsession.flush()

    recipe = Recipe(title="Tomatensalat")
    recipe.schedule = Schedule()
    dbsession.add(recipe)
    dbsession.flush()

    usage1 = IngredientUsage(
        recipe=recipe, ingredient=ingredient, amount="500", unit="g"
    )
    usage2 = IngredientUsage(
        recipe=recipe, ingredient=ingredient2, amount=None, unit=None
    )
    dbsession.add_all([usage1, usage2])

    week = Week()
    dbsession.add(week)
    dbsession.flush()

    day = Day(day=datetime.date(2026, 4, 21), week=week, dinner=recipe)
    dbsession.add(day)
    dbsession.flush()

    return week, recipe


def test_send_to_shopping_list_creates_todos(app_request, dbsession):
    week, _recipe = _make_week_with_recipe(dbsession)
    app_request.matchdict = {"id": str(week.id)}
    app_request.method = "POST"

    send_to_shopping_list(app_request)
    dbsession.flush()

    todos = dbsession.query(Todo).all()
    assert len(todos) == 2

    by_text = {t.text: t for t in todos}

    tomaten = by_text["Tomaten (500 g)"]
    assert tomaten.status == TodoStatus.todo
    assert "einkaufen:supermarkt:obst-u-gemuese" in tomaten.tags
    assert tomaten.note == "für: Tomatensalat"

    salz = by_text["Salz"]
    assert salz.status == TodoStatus.todo
    assert "Tomatensalat" in salz.note
    assert "einkaufen:supermarkt" in salz.tags


def test_send_to_shopping_list_aggregates_amounts_across_days(app_request, dbsession):
    ingredient = Ingredient(description="Mehl", tags=set())
    dbsession.add(ingredient)

    recipe1 = Recipe(title="Kuchen")
    recipe1.schedule = Schedule()
    recipe2 = Recipe(title="Brot")
    recipe2.schedule = Schedule()
    dbsession.add_all([recipe1, recipe2])
    dbsession.flush()

    dbsession.add(
        IngredientUsage(recipe=recipe1, ingredient=ingredient, amount="200", unit="g")
    )
    dbsession.add(
        IngredientUsage(recipe=recipe2, ingredient=ingredient, amount="300", unit="g")
    )

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


def test_send_to_shopping_list_untagged_ingredient_gets_sonstiges(
    app_request, dbsession
):
    ingredient = Ingredient(description="Wasser", tags=set())
    dbsession.add(ingredient)

    recipe = Recipe(title="Suppe")
    recipe.schedule = Schedule()
    dbsession.add(recipe)
    dbsession.flush()

    dbsession.add(
        IngredientUsage(recipe=recipe, ingredient=ingredient, amount="1", unit="l")
    )

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
    assert "einkaufen:supermarkt" in todos[0].tags


def _send_one(app_request, dbsession, tags):
    """Send a week with one ingredient tagged `tags`; return the todo's tags."""
    ingredient = Ingredient(description="Wasser", tags=tags)
    dbsession.add(ingredient)
    recipe = Recipe(title="Suppe")
    recipe.schedule = Schedule()
    dbsession.add(recipe)
    dbsession.flush()
    dbsession.add(
        IngredientUsage(recipe=recipe, ingredient=ingredient, amount="1", unit="l")
    )
    week = Week()
    dbsession.add(week)
    dbsession.flush()
    dbsession.add(Day(day=datetime.date(2026, 4, 21), week=week, dinner=recipe))
    dbsession.flush()

    app_request.matchdict = {"id": str(week.id)}
    send_to_shopping_list(app_request)
    dbsession.flush()
    (todo,) = dbsession.query(Todo).all()
    return todo.tags


def test_send_to_shopping_list_keeps_a_bare_einkaufen(app_request, dbsession):
    """Said to be bought, not where: that stays as it is."""
    assert _send_one(app_request, dbsession, {"einkaufen", "suppe"}) == {"einkaufen"}


def test_send_to_shopping_list_keeps_only_the_most_specific(app_request, dbsession):
    tags = {"einkaufen", "einkaufen:markt", "einkaufen:markt:obst", "einkaufenliste"}
    assert _send_one(app_request, dbsession, tags) == {"einkaufen:markt:obst"}


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
    assert response.location
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


def test_toggle_day_shopping_excludes_day(app_request, dbsession):
    week, _recipe = _make_week_with_recipe(dbsession)
    day = week.days[0]
    assert not day.exclude_from_shopping

    app_request.matchdict = {"day": day.id}
    toggle_day_shopping(app_request)
    dbsession.flush()

    assert day.exclude_from_shopping


def test_toggle_day_shopping_re_includes_day(app_request, dbsession):
    week, _recipe = _make_week_with_recipe(dbsession)
    day = week.days[0]
    day.exclude_from_shopping = True
    dbsession.flush()

    app_request.matchdict = {"day": day.id}
    toggle_day_shopping(app_request)
    dbsession.flush()

    assert not day.exclude_from_shopping


def test_excluded_day_skipped_in_shopping_list(app_request, dbsession):
    week, _recipe = _make_week_with_recipe(dbsession)
    day = week.days[0]
    day.exclude_from_shopping = True
    dbsession.flush()

    app_request.matchdict = {"id": str(week.id)}
    send_to_shopping_list(app_request)
    dbsession.flush()

    assert dbsession.query(Todo).count() == 0


# ---------------------------------------------------------------------------
# Recipe picker: sorted, title-only datalist
# ---------------------------------------------------------------------------


def test_recipe_picker_sorted_and_no_ids(authenticated_testapp, dbsession):
    r1 = Recipe(title="Zucchinisuppe", schedule=Schedule())
    r2 = Recipe(title="Apfelkuchen", schedule=Schedule())
    r3 = Recipe(title="Nudelauflauf", schedule=Schedule())
    dbsession.add_all([r1, r2, r3])
    week = Week()
    dbsession.add(week)
    dbsession.flush()
    dbsession.add(Day(day=datetime.date(2026, 5, 1), week=week))
    dbsession.flush()

    res = authenticated_testapp.get(f"/week/{week.id}/edit", status=200)
    body = res.text

    pos_apfel = body.index("Apfelkuchen")
    pos_nudel = body.index("Nudelauflauf")
    pos_zucchini = body.index("Zucchinisuppe")
    assert pos_apfel < pos_nudel < pos_zucchini

    # Option labels are titles only — no "ID – Title" pattern in the visible text.
    assert "–" not in body


def test_edit_week_sets_dinner_by_id(authenticated_testapp, dbsession):
    recipe = Recipe(title="Tomatensalat", schedule=Schedule())
    dbsession.add(recipe)
    week = Week()
    dbsession.add(week)
    dbsession.flush()
    day = Day(day=datetime.date(2026, 5, 2), week=week)
    dbsession.add(day)
    dbsession.flush()

    authenticated_testapp.post(
        f"/week/{week.id}/edit",
        {"dinner": str(recipe.id), "dinner_freestyle": "", "note": ""},
        status=303,
    )
    # Session is shared; day is the same Python object — no expire_all needed.
    assert day.dinner_id == recipe.id


def test_edit_week_empty_dinner_clears(authenticated_testapp, dbsession):
    recipe = Recipe(title="Gulasch", schedule=Schedule())
    dbsession.add(recipe)
    week = Week()
    dbsession.add(week)
    dbsession.flush()
    day = Day(day=datetime.date(2026, 5, 3), week=week, dinner=recipe)
    dbsession.add(day)
    dbsession.flush()

    authenticated_testapp.post(
        f"/week/{week.id}/edit",
        {"dinner": "", "dinner_freestyle": "", "note": ""},
        status=303,
    )
    # Session is shared; day is the same Python object — no expire_all needed.
    assert day.dinner_id is None


# ---------------------------------------------------------------------------
# Who the shopping list is for
# ---------------------------------------------------------------------------


def _team(dbsession, name):
    import datetime as _dt

    from menage2.models.team import Team

    team = Team(name=name, created_at=_dt.datetime.now(_dt.UTC))
    dbsession.add(team)
    dbsession.flush()
    return team


def test_the_shopping_list_goes_to_the_household(app_request, dbsession):
    """The name used to be spelled into the view; it still means this."""
    _team(dbsession, "haushalt")
    week, _ = _make_week_with_recipe(dbsession)
    app_request.matchdict = {"id": str(week.id)}
    app_request.method = "POST"

    send_to_shopping_list(app_request)
    dbsession.flush()

    tomaten = dbsession.query(Todo).filter(Todo.text == "Tomaten (500 g)").one()
    assert tomaten.assignees == {"haushalt"}


def test_the_shopping_list_can_be_pointed_somewhere_else(app_request, dbsession):
    from menage2.models.config import ConfigItem
    from menage2.views.planner import SHOPPING_ASSIGNEE

    _team(dbsession, "haushalt")
    _team(dbsession, "einkaufsteam")
    dbsession.add(ConfigItem(key=SHOPPING_ASSIGNEE, value="einkaufsteam"))
    week, _ = _make_week_with_recipe(dbsession)
    app_request.matchdict = {"id": str(week.id)}
    app_request.method = "POST"

    send_to_shopping_list(app_request)
    dbsession.flush()

    tomaten = dbsession.query(Todo).filter(Todo.text == "Tomaten (500 g)").one()
    assert tomaten.assignees == {"einkaufsteam"}


def test_the_shopping_list_survives_the_household_being_gone(app_request, dbsession):
    """Renaming that team away must not stop the list being made."""
    week, _ = _make_week_with_recipe(dbsession)
    app_request.matchdict = {"id": str(week.id)}
    app_request.method = "POST"

    send_to_shopping_list(app_request)
    dbsession.flush()

    tomaten = dbsession.query(Todo).filter(Todo.text == "Tomaten (500 g)").one()
    assert tomaten.assignees == set()


def _shop(app_request, dbsession, menu):
    """Cook `menu` on consecutive days and send it to the shopping list.

    `menu` is ``[(recipe title, [(ingredient, amount, unit), ...]), ...]``.
    Returns the shopping todos by text.
    """
    week = Week()
    dbsession.add(week)
    dbsession.flush()
    for offset, (title, uses) in enumerate(menu):
        recipe = Recipe(title=title)
        recipe.schedule = Schedule()
        dbsession.add(recipe)
        dbsession.flush()
        for ingredient, amount, unit in uses:
            dbsession.add(
                IngredientUsage(
                    recipe=recipe, ingredient=ingredient, amount=amount, unit=unit
                )
            )
        dbsession.add(
            Day(
                day=datetime.date(2026, 4, 21) + datetime.timedelta(days=offset),
                week=week,
                dinner=recipe,
            )
        )
    dbsession.flush()

    app_request.matchdict = {"id": str(week.id)}
    send_to_shopping_list(app_request)
    dbsession.flush()
    return {t.text: t for t in dbsession.query(Todo).all()}


def test_the_same_thing_without_an_amount_is_bought_once(app_request, dbsession):
    salz = Ingredient(description="Salz")
    dbsession.add(salz)

    todos = _shop(
        app_request,
        dbsession,
        [(title, [(salz, None, None)]) for title in ("Suppe", "Brot", "Pasta")],
    )

    assert list(todos) == ["Salz"]
    assert todos["Salz"].note == "für: Suppe, Brot, Pasta"


def test_the_same_thing_without_an_amount_but_separate_units_is_split(
    app_request, dbsession
):
    salz = Ingredient(description="Salz")
    dbsession.add(salz)

    todos = _shop(
        app_request,
        dbsession,
        [
            ("Suppe", [(salz, None, "Prise")]),
            ("Hühnchen", [(salz, None, None)]),
            ("Brot", [(salz, "etwas", None)]),
            ("Pasta", [(salz, "2", "Gramm")]),
        ],
    )

    assert list(todos) == ["Salz", "Salz (etwas)", "Salz (2 Gramm)"]
    assert todos["Salz"].note == "für: Suppe"
    assert todos["Salz (etwas)"].note == "für: Hühnchen, Brot (etwas)"
    assert todos["Salz (2 Gramm)"].note == "für: Pasta"


def test_amounts_in_the_same_unit_add_up_whatever_they_say(app_request, dbsession):
    """Numbers add up; "1/2" does not, so it is kept beside the total."""
    zucker = Ingredient(description="Zucker")
    dbsession.add(zucker)

    todos = _shop(
        app_request,
        dbsession,
        [
            ("Kuchen", [(zucker, "1", "TL")]),
            ("Tee", [(zucker, "1/2", "TL")]),
            ("Kaffee", [(zucker, "2", "TL")]),
        ],
    )

    assert list(todos) == ["Zucker (3 TL + 1/2 TL)"]
    note = todos["Zucker (3 TL + 1/2 TL)"].note
    assert note == "für: Kuchen (1 TL), Tee (1/2 TL), Kaffee (2 TL)"


def test_a_different_unit_is_a_different_item(app_request, dbsession):
    tomaten = Ingredient(description="Tomaten")
    dbsession.add(tomaten)

    todos = _shop(
        app_request,
        dbsession,
        [
            ("Salat", [(tomaten, "500", "g")]),
            ("Sauce", [(tomaten, "2", "Stück")]),
            ("Pizza", [(tomaten, "200", "g")]),
        ],
    )

    assert sorted(todos) == ["Tomaten (2 Stück)", "Tomaten (700 g)"]
    assert todos["Tomaten (2 Stück)"].note == "für: Sauce"


def test_a_recipe_cooked_twice_wants_twice_as_much(app_request, dbsession):
    mehl = Ingredient(description="Mehl")
    dbsession.add(mehl)

    todos = _shop(
        app_request,
        dbsession,
        [("Brot", [(mehl, "500", "g")]), ("Brot", [(mehl, "500", "g")])],
    )

    assert list(todos) == ["Mehl (1000 g)"]
    assert todos["Mehl (1000 g)"].note == "für: Brot"
