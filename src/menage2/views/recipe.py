import itertools
import uuid

import peppercorn
import sqlalchemy.orm
from pyramid.httpexceptions import HTTPSeeOther
from pyramid.view import view_config

from menage2.models import (
    Ingredient,
    IngredientUsage,
    Month,
    Recipe,
    RecipeSeasons,
    RecipeWeekDays,
    Weekday,
)


@view_config(
    route_name="suggest_ingredient",
    renderer="menage2:templates/suggest_ingredient.pt",
)
def suggest_ingredient(request):
    search = request.params.get("search")

    ingredients = (
        request.dbsession.query(Ingredient)
        .filter(Ingredient.description.op("like")(f"%{search}%"))
        .order_by(Ingredient.description)
        .all()
    )

    exact_match = len(
        [i for i in ingredients if i.description.lower() == search.lower()]
    )

    radio_uuid = uuid.uuid4().hex

    return {
        "ingredients": ingredients,
        "search": search,
        "exact_match": exact_match,
        "radio_uuid": radio_uuid,
    }


@view_config(
    route_name="list_recipes", renderer="menage2:templates/list_recipes.pt"
)
def list_recipes(request):
    recipes = (
        request.dbsession.query(Recipe)
        .filter(Recipe.active.is_(True))
        .options(
            sqlalchemy.orm.joinedload(Recipe.ingredients).joinedload(
                IngredientUsage.ingredient
            )
        )
    )
    return {"recipes": recipes}


@view_config(
    route_name="edit_recipe",
    renderer="menage2:templates/edit_recipe.pt",
    request_method="GET",
)
def show_recipe(request):
    recipe = (
        request.dbsession.query(Recipe)
        .filter(Recipe.id == int(request.matchdict["id"]))
        .options(
            sqlalchemy.orm.joinedload(Recipe.ingredients).joinedload(
                IngredientUsage.ingredient
            )
        )
    ).one()
    next_recipe = (
        request.dbsession.query(Recipe)
        .filter(Recipe.id > int(request.matchdict["id"]))
        .order_by(Recipe.id)
        .first()
    )
    previous_recipe = (
        request.dbsession.query(Recipe)
        .filter(Recipe.id < int(request.matchdict["id"]))
        .order_by(Recipe.id.desc())
        .first()
    )

    counter = itertools.count()
    return {
        "recipe": recipe,
        "next_recipe": next_recipe,
        "previous_recipe": previous_recipe,
        "weekdays": Weekday,
        "months": Month,
        "field_name": lambda x: x + ":" + str(next(counter)),
        "next_sequence": lambda: next(counter),
    }


@view_config(route_name="edit_recipe", request_method="POST")
def edit_recipe(request):
    fields = peppercorn.parse(request.params.items(), unique_key_separator=":")

    recipe = (
        request.dbsession.query(Recipe)
        .filter(Recipe.id == request.matchdict["id"])
        .options(
            sqlalchemy.orm.joinedload(Recipe.ingredients).joinedload(
                IngredientUsage.ingredient
            ),
            sqlalchemy.orm.joinedload(Recipe.seasons),
            sqlalchemy.orm.joinedload(Recipe.schedule),
            sqlalchemy.orm.joinedload(Recipe.weekdays),
        )
    ).one()

    recipe.title = fields["title"]
    recipe.active = bool(fields.get("active"))
    recipe.source = fields["source"]
    recipe.source_url = fields["source_url"]
    recipe.note = fields["note"]
    recipe.schedule.frequency = int(fields["frequency"])

    weekdays = fields["weekdays"]
    recipe.weekdays = [
        RecipeWeekDays(recipe=recipe, weekday=Weekday(int(weekday)))
        for weekday in weekdays
    ]

    seasons = fields["seasons"]
    recipe.seasons = [
        RecipeSeasons(recipe=recipe, month=Month(int(month)))
        for month in seasons
    ]

    ingredients = []
    for ingredient in fields["ingredients"]:
        ingredient_id = ingredient["ingredient_id"]
        if not ingredient_id:
            continue
        elif ingredient["ingredient_id"] == "new":
            ingredient_obj = Ingredient(description=ingredient["ingredient"])
        else:
            ingredient_id = int(ingredient_id)
            ingredient_obj = (
                request.dbsession.query(Ingredient)
                .filter(Ingredient.id == ingredient_id)
                .one()
            )

        usage = IngredientUsage(
            amount=ingredient["amount"],
            ingredient=ingredient_obj,
            unit=ingredient["unit"],
        )
        ingredients.append(usage)

    recipe.ingredients = ingredients

    return HTTPSeeOther(request.route_url("edit_recipe", id=recipe.id))


@view_config(route_name="add_recipe", request_method="PUT")
def add_recipe(request):
    recipe = Recipe()
    recipe.title = "Neues Rezept"
    request.dbsession.add(recipe)
    request.dbsession.flush()
    return HTTPSeeOther(request.route_url("edit_recipe", id=recipe.id))
