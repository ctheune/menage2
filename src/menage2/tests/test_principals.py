"""Users and teams share one namespace, and the database is what says so."""

import datetime

import pytest
import sqlalchemy.exc
from sqlalchemy import select

from menage2.models.principal import Principal
from menage2.models.team import Team
from menage2.models.user import User


def _now():
    return datetime.datetime.now(datetime.UTC)


def _user(dbsession, username: str) -> User:
    user = User(
        username=username,
        real_name=username.title(),
        email=f"{username}@example.com",
        created_at=_now(),
    )
    dbsession.add(user)
    dbsession.flush()
    return user


def test_a_user_gets_a_principal_wherever_it_is_made(dbsession):
    """Not only through the admin: tests and scripts make users too."""
    user = _user(dbsession, "greta")

    assert user.principal.name == "greta"
    assert user.principal.kind == "user"
    assert user.principal.user_id == user.id


def test_a_team_gets_a_principal(dbsession):
    team = Team(name="garten", created_at=_now())
    dbsession.add(team)
    dbsession.flush()

    assert team.principal.name == "garten"
    assert team.principal.kind == "team"


def test_renaming_a_user_renames_its_principal(dbsession):
    user = _user(dbsession, "greta")
    principal_id = user.principal.id

    user.username = "margarete"
    dbsession.flush()

    principal = dbsession.get(Principal, principal_id)
    assert principal.name == "margarete"


def test_a_team_cannot_take_a_username(dbsession):
    """The check the admin views make by hand, made by the database."""
    _user(dbsession, "greta")

    dbsession.add(Team(name="greta", created_at=_now()))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        dbsession.flush()


def test_deleting_a_user_takes_its_principal_with_it(dbsession):
    user = _user(dbsession, "greta")
    principal_id = user.principal.id

    dbsession.delete(user)
    dbsession.flush()

    assert dbsession.get(Principal, principal_id) is None


def test_every_user_and_team_has_exactly_one_principal(dbsession, admin_user):
    dbsession.add(Team(name="haushalt", created_at=_now()))
    dbsession.flush()

    users = dbsession.execute(select(User)).scalars().all()
    teams = dbsession.execute(select(Team)).scalars().all()
    principals = dbsession.execute(select(Principal)).scalars().all()

    assert len(principals) == len(users) + len(teams)
    assert {p.name for p in principals} == {u.username for u in users} | {
        t.name for t in teams
    }
