from sqlalchemy import Column, Integer, Text, ForeignKey, Date
from sqlalchemy.orm import relationship, backref
import datetime

from .meta import Base

from menage2.models import Recipe, ConfigItem, IngredientUsage

from sqlalchemy.orm.session import Session
from sqlalchemy.orm import contains_eager

import os
import enum

from sqlalchemy import Enum

from rtmapi import Rtm


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
    days = relationship(
        "Day", cascade="all, delete-orphan", order_by="Day.day", back_populates="week"
    )

    @property
    def first(self):
        return self.days[0]

    @property
    def last(self):
        return self.days[-1]

    def send_to_rtm(self):
        api_key = os.environ["RTM_API_KEY"]
        shared_secret = os.environ["RTM_SHARED_SECRET"]
        list_id = "24309112"
        session = Session.object_session(self)
        token = session.query(ConfigItem).filter(ConfigItem.key == "RTM_TOKEN").one()
        api = Rtm(api_key, shared_secret, "write", token.value)
        if not api.token_valid():
            raise RuntimeError("Invalid RTM token, please log in first.")

        result = api.rtm.timelines.create()
        timeline = result.timeline.value

        shopping_list = []

        ingredients = {}

        for day in self.days:
            if not day.dinner:
                continue
            for ingredient_usage in day.dinner.ingredients:
                amount = ingredient_usage.numeric_amount()
                if not amount:
                    shopping_list.append(ingredient_usage)
                    continue

                unit = ingredient_usage.unit or ""

                by_unit = ingredients.setdefault(ingredient_usage.ingredient, {})
                by_unit.setdefault(unit, 0)
                by_unit[unit] += amount

        for ingredient, by_unit in ingredients.items():
            for unit, amount in by_unit.items():
                usage = IngredientUsage()
                usage.ingredient = ingredient
                usage.unit = unit
                usage.amount = str(amount)
                shopping_list.append(usage)

        for item in shopping_list:
            api.rtm.tasks.add(
                timeline=timeline,
                list_id=list_id,
                name=item.to_shopping_list(),
            )


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
    week = relationship("Week", back_populates="days")
    dinner_id = Column(Integer, ForeignKey("recipes.id"))
    dinner = relationship(
        "Recipe", uselist=False, backref=backref("days", order_by="Day.day")
    )

    dinner_freestyle = Column(Text)

    note = Column(Text)

    @property
    def id(self):
        return self.day.strftime("%Y-%m-%d")

    def is_today(self):
        return self.day == datetime.date.today()

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
