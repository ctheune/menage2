from sqlalchemy import Column, Integer, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship, backref

from .meta import Base

from .. import models
from menage2.utils import Seen


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
    ingredient_id = Column(
        Integer, ForeignKey("ingredients.id"), nullable=False
    )
    ingredient = relationship(
        "Ingredient", uselist=False, backref=backref("used")
    )

    amount: str = Column(Text)
    unit: str = Column(Text)

    def to_string(self):
        return " ".join(
            filter(None, [self.amount, self.unit, self.ingredient.description])
        )

    def to_shopping_list(self):
        result = self.ingredient.description
        amount = " ".join(
            filter(
                None,
                [
                    self.amount,
                    self.unit,
                ],
            )
        )
        if amount:
            result += " (" + amount + ")"
        return result

    def numeric_amount(self) -> float | int | None:
        try:
            return int(self.amount)
        except (ValueError, TypeError):
            try:
                return float(self.amount)
            except (ValueError, TypeError):
                pass
        return None


KNOWN_TAGS = set(["obst-u-gemuese", "kühlung"])


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True)
    description = Column(Text)
    tags = Column(Text)  # comma separated list of tags to use for RTM

    @property
    def hashtags(self):
        if not self.tags:
            return []
        return [f"#{tag.strip()}" for tag in self.tags.split(",")]

    @property
    def recipes(self):
        result = []
        seen_recipes = Seen()
        for recipe in (usage.recipe for usage in self.used):
            if recipe.id in seen_recipes:
                continue
            result.append(recipe)
        return result
