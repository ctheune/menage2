from pyramid.view import view_config
from sqlalchemy.sql import func

from menage2.models import (
    Ingredient,
)


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
