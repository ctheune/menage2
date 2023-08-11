import argparse
import sys
import datetime

from pyramid.paster import bootstrap, setup_logging
from sqlalchemy.exc import OperationalError
from sqlalchemy import text, create_engine, delete

from .. import models


def setup_models(dbsession):
    """
    Add or update models / fixtures in the database.

    """
    # dbsession.execute(delete(models.Recipe))
    # dbsession.execute(delete(models.IngredientUsage))
    # dbsession.execute(delete(models.Ingredient))
    # dbsession.execute(delete(models.Week))
    # dbsession.execute(delete(models.Day))

    # engine = create_engine("sqlite+pysqlite:///db.sqlite3", echo=False)
    # with engine.connect() as conn:
    #     print("Ingredients")
    #     for ingredient in conn.execute(text("select * from recipedb_ingredient")):
    #         ingredient = models.Ingredient(**ingredient._asdict())
    #         dbsession.add(ingredient)

    #     print("Recipes")
    #     for recipe in conn.execute(text("select * from recipedb_recipe")):
    #         recipe = models.Recipe(**recipe._asdict())
    #         dbsession.add(recipe)

    #     print("Recipe ingredients")
    #     for ingredientusage in conn.execute(
    #         text("select * from recipedb_ingredientusage")
    #     ):
    #         ingredientusage = models.IngredientUsage(**ingredientusage._asdict())
    #         dbsession.add(ingredientusage)

    #     print("Weeks")
    #     for week in conn.execute(text("select * from weekplanner_week")):
    #         week = models.Week(**week._asdict())
    #         dbsession.add(week)

    #     print("Days")
    #     for day in conn.execute(text("select * from weekplanner_day")):
    #         day = day._asdict()
    #         del day["id"]
    #         day["day"] = datetime.date.fromisoformat(day["day"])
    #         day = models.Day(**day)
    #         dbsession.add(day)

    # Enable all days


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config_uri",
        help="Configuration file, e.g., development.ini",
    )
    return parser.parse_args(argv[1:])


def main(argv=sys.argv):
    args = parse_args(argv)
    setup_logging(args.config_uri)
    env = bootstrap(args.config_uri)

    try:
        with env["request"].tm:
            dbsession = env["request"].dbsession
            setup_models(dbsession)
    except OperationalError:
        print(
            """
Pyramid is having a problem using your SQL database.  The problem
might be caused by one of the following things:

1.  You may need to initialize your database tables with `alembic`.
    Check your README.txt for description and try to run it.

2.  Your database server may not be running.  Check that the
    database server referred to by the "sqlalchemy.url" setting in
    your "development.ini" file is running.
            """
        )
