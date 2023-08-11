from sqlalchemy import Column, Integer, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship, backref

from .meta import Base

from .. import models


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True)

    active = Column(Boolean, server_default="1")

    title = Column(Text, nullable=False)

    note = Column(Text)
    source = Column(Text)
    source_url = Column(Text)

    def __init__(self):
        self.schedule = models.Schedule()

    # XXX those are helpers that the form library should take over
    @property
    def enum_weekdays(self):
        return [w.weekday for w in self.weekdays]

    @property
    def enum_seasons(self):
        return [s.month for s in self.seasons]

    @property
    def last_cooked(self):
        pass


class IngredientUsage(Base):
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    recipe = relationship(
        "Recipe",
        uselist=False,
        backref=backref("ingredients", cascade="all, delete-orphan"),
    )
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    ingredient = relationship("Ingredient", uselist=False, backref=backref("recipes"))

    amount = Column(Text)
    unit = Column(Text)

    # @classmethod
    # def from_shortcut(cls, recipe, shortcut):
    #     parts = shortcut.split(" ", 2)
    #     if len(parts) == 1:
    #         amount = None
    #         unit = None
    #         ingredient = parts[0]
    #     elif len(parts) == 2:
    #         amount = parts[0]
    #         unit = None
    #         ingredient = parts[1]
    #     else:
    #         amount, unit, ingredient = parts

    #     if unit is None:
    #         unit = ""

    #     ing_obj, _ = Ingredient.objects.get_or_create(description=ingredient)

    #     print(recipe, amount, unit, ing_obj)
    #     usage = IngredientUsage.objects.create(
    #         recipe=recipe, amount=amount, unit=unit, ingredient=ing_obj
    #     )
    #     usage.save()


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True)
    description = Column(Text)
