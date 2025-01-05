import itertools
import uuid
from sqlalchemy.sql import func
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
    route_name="list_ingredients",
    renderer="menage2:templates/list_ingredients.pt",
)
def list_ingredients(request):
    ingredients = request.dbsession.query(Ingredient).order_by(
        func.LOWER(Ingredient.description)
    )
    return {"ingredients": ingredients}


@view_config(
    route_name="ingredient_recipes",
    renderer="menage2:templates/ingredient_recipes.pt",
)
def list_ingredient_recipes(request):
    ingredient_id = int(request.matchdict["id"])
    ingredient = (
        request.dbsession.query(Ingredient)
        .filter(Ingredient.id == ingredient_id)
        .one()
    )
    return {"recipes": ingredient.recipes}
