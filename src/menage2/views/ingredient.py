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

    def tags(ingredient):
        for tag in sorted(ingredient.KNOWN_TAGS):
            yield TagToggle(tag, tag in ingredient.tags_set)

    return {"ingredients": ingredients, "tags": tags}


class TagToggle:
    inactive_color = "bg-slate-400"
    active_color = "bg-cyan-400"

    def __init__(self, name: str, active: bool):
        self.name = name
        self.active = active

    @property
    def color(self):
        return self.active_color if self.active else self.inactive_color


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


@view_config(
    request_method="PATCH",
    route_name="ingredient_toggle_tag",
)
def toggle_ingredient_tag(request):
    ingredient_id = int(request.matchdict["id"])
    ingredient = (
        request.dbsession.query(Ingredient)
        .filter(Ingredient.id == ingredient_id)
        .one()
    )
    tag = request.matchdict["tag"]
    if tag in ingredient.tags_set:
        ingredient.tags_set = ingredient.tags_set - set([tag])
    else:
        ingredient.tags_set = ingredient.tags_set | set([tag])
    return HTTPSeeOther(request.route_url("list_ingredients"))
