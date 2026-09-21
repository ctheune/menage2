import itertools
import json
import uuid

import peppercorn
import sqlalchemy.orm
from pyramid.httpexceptions import HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.sql import func

from menage2.models import (
    Ingredient,
    IngredientUsage,
    Month,
    Recipe,
    RecipeSeasons,
    RecipeWeekDays,
    Weekday,
)
from menage2.views.todo import files_of


@view_config(
    route_name="list_ingredients",
    renderer="menage2:templates/list_ingredients.pt",
)
def list_ingredients(request):
    """Every ingredient, by name.

    Sorted through the base table: the name is the item's text now, and an
    ingredient is an item.
    """
    ingredients = request.dbsession.query(Ingredient).order_by(
        func.lower(Ingredient.description)
    )
    return {"ingredients": ingredients}


@view_config(
    route_name="ingredient_recipes",
    renderer="menage2:templates/ingredient_recipes.pt",
)
def list_ingredient_recipes(request):
    ingredient_id = int(request.matchdict["id"])
    ingredient = (
        request.dbsession.query(Ingredient).filter(Ingredient.id == ingredient_id).one()
    )
    return {"recipes": ingredient.recipes}


@view_config(
    route_name="ingredient_panel",
    request_method="GET",
    renderer="menage2:templates/_ingredient_panel.pt",
)
def ingredient_panel(request):
    """The editor for one ingredient: the same fields anything else gets."""
    ingredient = _get(request)
    return {
        "ingredient": ingredient,
        "tags_json": json.dumps(sorted(ingredient.tags)),
        **files_of(request, ingredient),
    }


@view_config(
    route_name="ingredient_update",
    request_method="POST",
    renderer="menage2:templates/list_ingredients.pt",
)
def update_ingredient(request):
    """Save what the panel changed and give the row back.

    Tags arrive as `tags[]` from the shared field, which is why there is
    nothing ingredient-shaped about reading them.
    """
    ingredient = _get(request)
    if "tags" in request.params.getall("clear_fields[]"):
        ingredient.tags = set()
    else:
        ingredient.tags = set(request.params.getall("tags[]"))
    request.dbsession.flush()
    return list_ingredients(request)


def _get(request) -> Ingredient:
    ingredient = request.dbsession.get(Ingredient, int(request.matchdict["id"]))
    if ingredient is None:
        raise HTTPNotFound()
    return ingredient
