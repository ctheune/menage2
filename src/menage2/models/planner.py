from sqlalchemy import Column, Integer, Text, ForeignKey, Date
from sqlalchemy.orm import relationship, backref
import datetime

from .meta import Base

from menage2.models import Recipe

from sqlalchemy.orm.session import Session
from sqlalchemy.orm import contains_eager

import enum

from sqlalchemy import Enum


class Weekday(enum.Enum):
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


class Month(enum.Enum):
    JANUARY = 1
    FEBRUARY = 2
    MARCH = 3
    APRIL = 4
    MAY = 5
    JUNE = 6
    JULY = 7
    AUGUST = 8
    SEPTEMBER = 9
    OCTOBER = 10
    NOVEMBER = 11
    DECEMBER = 12


class Week(Base):
    __tablename__ = "planner_weeks"

    id = Column(Integer, primary_key=True)

    @property
    def first(self):
        return list(sorted(self.days, key=lambda x: x.day))[0]

    @property
    def last(self):
        return list(sorted(self.days, key=lambda x: x.day))[-1]


class Schedule(Base):
    __tablename__ = "schedules"

    recipe_id = Column(Integer, ForeignKey("recipes.id"), primary_key=True)
    recipe = relationship(
        "Recipe",
        uselist=False,
        backref=backref("schedule", uselist=False, cascade="all, delete-orphan"),
    )

    frequency = Column(Integer, server_default="90")

    @property
    def due_ratio(self):
        if not self.recipe.days:
            return 1.5
        elapsed = (datetime.date.today() - self.recipe.days[-1].day).days
        ratio = elapsed / self.frequency
        return ratio


class RecipeSeasons(Base):
    __tablename__ = "recipes_seasons"

    recipe_id = Column(Integer, ForeignKey("recipes.id"), primary_key=True)
    recipe = relationship(
        "Recipe",
        uselist=False,
        backref=backref("seasons", cascade="all, delete-orphan"),
    )
    month = Column(Enum(Month), primary_key=True)


class RecipeWeekDays(Base):
    __tablename__ = "recipe_weekdays"

    recipe_id = Column(Integer, ForeignKey("recipes.id"), primary_key=True)
    recipe = relationship(
        "Recipe",
        uselist=False,
        backref=backref("weekdays", cascade="all, delete-orphan"),
    )

    weekday = Column(Enum(Weekday), primary_key=True)


class Day(Base):
    __tablename__ = "planner_days"

    day = Column(Date, primary_key=True)

    week_id = Column(Integer, ForeignKey("planner_weeks.id"), nullable=False)
    week = relationship("Week", uselist=False, backref=backref("days"))

    dinner_id = Column(Integer, ForeignKey("recipes.id"))
    dinner = relationship(
        "Recipe", uselist=False, backref=backref("days", order_by="Day.day")
    )

    dinner_freestyle = Column(Text)

    note = Column(Text)

    @property
    def weekday(self) -> Weekday:
        return Weekday(self.day.isoweekday())

    @property
    def season(self) -> Month:
        return Month(self.day.month)

    def suggestions(self, count=5):
        session = Session.object_session(self)
        recipes = (
            session.query(Recipe)
            .join(Recipe.weekdays)
            .join(Recipe.seasons)
            .options(contains_eager(Recipe.weekdays))
            .options(contains_eager(Recipe.seasons))
            .filter(
                (Recipe.active.is_(True))
                & (RecipeWeekDays.weekday == self.weekday)
                & (RecipeSeasons.month == self.season)
            )
            .all()
        )
        recipes = list(recipes)
        recipes.sort(key=lambda r: r.schedule.due_ratio, reverse=True)
        return recipes[:count]

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
