"""Recording that somebody is away, and who picks up their team's work."""

import datetime

import pytest

from menage2.models.team import Team, TeamMember
from menage2.models.user import Absence, User
from menage2.principals import (
    absent_usernames,
    get_user_team_memberships,
    todo_matches_filter,
    uncovered_teams,
)

# 2026-08-10 is a Monday, so the week runs Mon 10th to Fri 14th.
MONDAY = datetime.date(2026, 8, 10)
TUESDAY = datetime.date(2026, 8, 11)
FRIDAY = datetime.date(2026, 8, 14)
SATURDAY_BEFORE = datetime.date(2026, 8, 8)
SUNDAY_BEFORE = datetime.date(2026, 8, 9)
SATURDAY_AFTER = datetime.date(2026, 8, 15)
SUNDAY_AFTER = datetime.date(2026, 8, 16)
FRIDAY_BEFORE = datetime.date(2026, 8, 7)
MONDAY_AFTER = datetime.date(2026, 8, 17)


def _absence(starts, ends):
    return Absence(starts_on=starts, ends_on=ends)


# ---------------------------------------------------------------------------
# Which days an absence covers
# ---------------------------------------------------------------------------


def test_both_days_are_inclusive():
    away = _absence(TUESDAY, datetime.date(2026, 8, 13))
    assert away.covers(TUESDAY)
    assert away.covers(datetime.date(2026, 8, 13))
    assert not away.covers(datetime.date(2026, 8, 14))


def test_a_single_day():
    away = _absence(TUESDAY, TUESDAY)
    assert away.covers(TUESDAY)
    assert not away.covers(datetime.date(2026, 8, 12))


def test_starting_on_a_monday_takes_the_weekend_before():
    """Nobody books the Saturday to say they will not be working."""
    away = _absence(MONDAY, TUESDAY)
    assert away.covers(SATURDAY_BEFORE)
    assert away.covers(SUNDAY_BEFORE)
    assert not away.covers(FRIDAY_BEFORE)


def test_ending_on_a_friday_takes_the_weekend_after():
    away = _absence(TUESDAY, FRIDAY)
    assert away.covers(SATURDAY_AFTER)
    assert away.covers(SUNDAY_AFTER)
    assert not away.covers(MONDAY_AFTER)


def test_a_whole_week_takes_both_weekends():
    away = _absence(MONDAY, FRIDAY)
    assert away.covers_from == SATURDAY_BEFORE
    assert away.covers_until == SUNDAY_AFTER
    for day in (SATURDAY_BEFORE, MONDAY, FRIDAY, SUNDAY_AFTER):
        assert away.covers(day), day


@pytest.mark.parametrize(
    "starts, ends",
    [
        (TUESDAY, datetime.date(2026, 8, 13)),  # Tue–Thu, no weekend either side
        (SATURDAY_BEFORE, SUNDAY_BEFORE),  # the weekend itself
    ],
)
def test_other_stretches_are_left_as_they_are(starts, ends):
    away = _absence(starts, ends)
    assert away.covers_from == starts
    assert away.covers_until == ends


# ---------------------------------------------------------------------------
# Who is away
# ---------------------------------------------------------------------------


def _user(dbsession, username):
    user = User(
        username=username,
        real_name=username.title(),
        email=f"{username}@test.local",
        is_active=True,
    )
    dbsession.add(user)
    dbsession.flush()
    return user


def _away(dbsession, user, starts, ends):
    absence = Absence(user_id=user.id, starts_on=starts, ends_on=ends)
    dbsession.add(absence)
    dbsession.flush()
    return absence


def test_nobody_away_is_nobody(dbsession):
    assert absent_usernames(dbsession, MONDAY) == set()


def test_who_is_away_on_a_day(dbsession):
    alice = _user(dbsession, "alice")
    bob = _user(dbsession, "bob")
    _away(dbsession, alice, TUESDAY, FRIDAY)
    _away(dbsession, bob, MONDAY_AFTER, MONDAY_AFTER)

    assert absent_usernames(dbsession, TUESDAY) == {"alice"}
    assert absent_usernames(dbsession, MONDAY_AFTER) == {"bob"}


def test_somebody_deactivated_is_away_for_good(dbsession):
    """They are not coming back on Monday, and their team should not wait."""
    gone = _user(dbsession, "gone")
    gone.is_active = False
    dbsession.flush()

    assert absent_usernames(dbsession, MONDAY) == {"gone"}
    assert absent_usernames(dbsession, MONDAY + datetime.timedelta(days=365)) == {
        "gone"
    }


def test_a_teams_work_moves_on_when_its_only_assignee_is_deactivated(dbsession):
    gone, boss = _user(dbsession, "gone"), _user(dbsession, "boss")
    _team(dbsession, "kinder", assignees=[gone], supervisors=[boss])
    gone.is_active = False
    dbsession.flush()

    assert _covered(dbsession, boss, TUESDAY) == {"kinder"}


def test_the_weekend_rule_reaches_the_query_too(dbsession):
    """The stretch is widened in Python, so the query has to look wider."""
    alice = _user(dbsession, "alice")
    _away(dbsession, alice, MONDAY, FRIDAY)

    assert absent_usernames(dbsession, SATURDAY_BEFORE) == {"alice"}
    assert absent_usernames(dbsession, SUNDAY_AFTER) == {"alice"}
    assert absent_usernames(dbsession, FRIDAY_BEFORE) == set()
    assert absent_usernames(dbsession, MONDAY_AFTER) == set()


# ---------------------------------------------------------------------------
# Whose work a supervisor picks up
# ---------------------------------------------------------------------------


def _team(dbsession, name, assignees=(), supervisors=()):
    team = Team(name=name)
    dbsession.add(team)
    dbsession.flush()
    for user in assignees:
        dbsession.add(TeamMember(team_id=team.id, user_id=user.id, role="assignee"))
    for user in supervisors:
        dbsession.add(TeamMember(team_id=team.id, user_id=user.id, role="supervisor"))
    dbsession.flush()
    return team


def _covered(dbsession, boss, day):
    return uncovered_teams(
        dbsession, boss, get_user_team_memberships(dbsession, boss), day
    )


def test_a_team_with_somebody_still_there_is_covered(dbsession):
    alice, bob, boss = (_user(dbsession, n) for n in ("alice", "bob", "boss"))
    _team(dbsession, "kinder", assignees=[alice, bob], supervisors=[boss])
    _away(dbsession, alice, TUESDAY, FRIDAY)

    assert _covered(dbsession, boss, TUESDAY) == set()


def test_a_team_with_everybody_away_is_not(dbsession):
    alice, bob, boss = (_user(dbsession, n) for n in ("alice", "bob", "boss"))
    _team(dbsession, "kinder", assignees=[alice, bob], supervisors=[boss])
    _away(dbsession, alice, TUESDAY, FRIDAY)
    _away(dbsession, bob, TUESDAY, FRIDAY)

    assert _covered(dbsession, boss, TUESDAY) == {"kinder"}
    # And back to normal the day they return.
    assert _covered(dbsession, boss, MONDAY_AFTER) == set()


def test_a_team_with_nobody_assigned_is_not_a_holiday(dbsession):
    """An empty team is a setup left half done."""
    boss = _user(dbsession, "boss")
    _team(dbsession, "empty", supervisors=[boss])

    assert _covered(dbsession, boss, TUESDAY) == set()


def test_only_the_teams_you_supervise(dbsession):
    alice, boss = _user(dbsession, "alice"), _user(dbsession, "boss")
    _team(dbsession, "kinder", assignees=[alice])
    _away(dbsession, alice, TUESDAY, FRIDAY)

    assert _covered(dbsession, boss, TUESDAY) == set()


def test_nobody_holds_two_roles_in_one_team(dbsession):
    """Which is why standing in for yourself never comes up."""
    import sqlalchemy.exc

    boss = _user(dbsession, "boss")
    team = _team(dbsession, "kinder", supervisors=[boss])
    dbsession.add(TeamMember(team_id=team.id, user_id=boss.id, role="assignee"))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        dbsession.flush()
    dbsession.rollback()


# ---------------------------------------------------------------------------
# What that does to the list
# ---------------------------------------------------------------------------


class _Todo:
    """Enough of a todo for the filter: who it belongs to and who it is for.

    It needs a real owner — an unowned one lands on everybody's list by a
    different rule, which would hide whether covering did anything.
    """

    def __init__(self, assignees, owner):
        self.assignees = set(assignees)
        self.owner = owner


def test_a_covered_teams_work_stays_off_my_tasks(dbsession):
    boss, alice = _user(dbsession, "boss"), _user(dbsession, "alice")
    todo = _Todo({"kinder"}, owner=alice)
    assert not todo_matches_filter(
        todo, boss, {"kinder": "supervisor"}, "personal", covering=set()
    )


def test_an_uncovered_teams_work_lands_on_my_tasks(dbsession):
    boss, alice = _user(dbsession, "boss"), _user(dbsession, "alice")
    todo = _Todo({"kinder"}, owner=alice)
    assert todo_matches_filter(
        todo, boss, {"kinder": "supervisor"}, "personal", covering={"kinder"}
    )


def test_covering_a_team_does_not_bring_in_other_work(dbsession):
    boss, alice = _user(dbsession, "boss"), _user(dbsession, "alice")
    todo = _Todo({"eltern"}, owner=alice)
    assert not todo_matches_filter(
        todo, boss, {"kinder": "supervisor"}, "personal", covering={"kinder"}
    )


def test_covering_does_not_change_the_other_lists(dbsession):
    """It is still delegated work; it has just landed on somebody."""
    boss, alice = _user(dbsession, "boss"), _user(dbsession, "alice")
    todo = _Todo({"kinder"}, owner=alice)
    assert todo_matches_filter(
        todo, boss, {"kinder": "supervisor"}, "delegated_out", covering={"kinder"}
    )
    assert not todo_matches_filter(
        todo, boss, {"kinder": "supervisor"}, "delegated_in", covering={"kinder"}
    )


# ---------------------------------------------------------------------------
# Recording one, from either end
# ---------------------------------------------------------------------------


def test_the_account_page_shows_your_own(authenticated_testapp, dbsession, admin_user):
    _away(dbsession, admin_user, TUESDAY, FRIDAY)
    dbsession.flush()

    res = authenticated_testapp.get("/account", status=200)

    assert b"Away" in res.body
    assert b"11 Aug 2026" in res.body
    # The Friday end reaches over the weekend, and the page says so.
    assert b"16 Aug" in res.body


def test_recording_one_on_the_account_page(
    authenticated_testapp, dbsession, admin_user
):
    authenticated_testapp.post(
        "/account/absences",
        {"starts_on": "2026-08-11", "ends_on": "2026-08-14"},
        status=303,
    )

    dbsession.expire_all()
    assert [(a.starts_on, a.ends_on) for a in admin_user.absences] == [
        (TUESDAY, FRIDAY)
    ]


def test_the_last_day_cannot_come_first(authenticated_testapp, dbsession, admin_user):
    res = authenticated_testapp.post(
        "/account/absences",
        {"starts_on": "2026-08-14", "ends_on": "2026-08-11"},
        status=303,
    )

    assert "error=" in res.location
    dbsession.expire_all()
    assert admin_user.absences == []


def test_removing_your_own(authenticated_testapp, dbsession, admin_user):
    absence = _away(dbsession, admin_user, TUESDAY, FRIDAY)
    dbsession.flush()

    authenticated_testapp.post(f"/account/absences/{absence.id}/remove", status=303)

    dbsession.expire_all()
    assert admin_user.absences == []


def test_you_cannot_remove_somebody_elses(authenticated_testapp, dbsession, admin_user):
    someone = _user(dbsession, "someone")
    absence = _away(dbsession, someone, TUESDAY, FRIDAY)
    dbsession.flush()

    authenticated_testapp.post(f"/account/absences/{absence.id}/remove", status=404)

    dbsession.expire_all()
    assert len(someone.absences) == 1


def test_an_admin_records_one_for_somebody_else(
    authenticated_testapp, dbsession, admin_user
):
    someone = _user(dbsession, "someone")
    dbsession.flush()

    res = authenticated_testapp.get(f"/admin/users/{someone.id}/absences", status=200)
    assert b"Someone" in res.body

    authenticated_testapp.post(
        f"/admin/users/{someone.id}/absences/add",
        {"starts_on": "2026-08-11", "ends_on": "2026-08-14"},
        status=303,
    )

    dbsession.expire_all()
    assert [(a.starts_on, a.ends_on) for a in someone.absences] == [(TUESDAY, FRIDAY)]


def test_absences_are_nobody_elses_business(user_testapp, dbsession, admin_user):
    user_testapp.get(f"/admin/users/{admin_user.id}/absences", status=403)


# ---------------------------------------------------------------------------
# What a supervisor actually sees
# ---------------------------------------------------------------------------


def _todo_for(dbsession, text, assignees, owner):
    from menage2.models.todo import Todo, TodoStatus

    todo = Todo(
        text=text,
        tags=set(),
        assignees=set(assignees),
        status=TodoStatus.todo,
        owner=owner,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(todo)
    dbsession.flush()
    return todo


def _mine(dbsession, user, day):
    from menage2.views.todo import _filter_todos

    return [t.text for t in _filter_todos(dbsession, day, user=user)]


def test_a_teams_work_arrives_when_everyone_is_away(dbsession, admin_user):
    """The whole point of the feature."""
    alice = _user(dbsession, "alice")
    _team(dbsession, "kinder", assignees=[alice], supervisors=[admin_user])
    _todo_for(dbsession, "Feed the cat", {"kinder"}, owner=alice)

    assert _mine(dbsession, admin_user, TUESDAY) == []

    _away(dbsession, alice, TUESDAY, FRIDAY)

    assert _mine(dbsession, admin_user, TUESDAY) == ["Feed the cat"]


def test_and_leaves_again_when_they_are_back(dbsession, admin_user):
    alice = _user(dbsession, "alice")
    _team(dbsession, "kinder", assignees=[alice], supervisors=[admin_user])
    _todo_for(dbsession, "Feed the cat", {"kinder"}, owner=alice)
    _away(dbsession, alice, TUESDAY, FRIDAY)

    # Friday's end reaches over the weekend, so Monday is the first day back.
    assert _mine(dbsession, admin_user, SUNDAY_AFTER) == ["Feed the cat"]
    assert _mine(dbsession, admin_user, MONDAY_AFTER) == []


def test_one_of_them_still_there_keeps_it_off_the_list(dbsession, admin_user):
    alice, bob = _user(dbsession, "alice"), _user(dbsession, "bob")
    _team(dbsession, "kinder", assignees=[alice, bob], supervisors=[admin_user])
    _todo_for(dbsession, "Feed the cat", {"kinder"}, owner=alice)
    _away(dbsession, alice, TUESDAY, FRIDAY)

    assert _mine(dbsession, admin_user, TUESDAY) == []


def test_the_row_says_whose_work_it_is(authenticated_testapp, dbsession, admin_user):
    """A task nobody has seen before, turning up unexplained, is not obviously
    yours to do only until they are back."""
    alice = _user(dbsession, "alice")
    _team(dbsession, "kinder", assignees=[alice], supervisors=[admin_user])
    _todo_for(dbsession, "Feed the cat", {"kinder"}, owner=alice)
    today = datetime.date.today()
    _away(dbsession, alice, today, today)
    dbsession.flush()

    res = authenticated_testapp.get("/todos/groups", status=200)

    assert b"Feed the cat" in res.body
    assert b"covering @kinder" in res.body
    # And says it instead of the assignee, which would only repeat the team.
    # (The row also carries the assignees in a data attribute, which is what
    # the edit form reads — hence matching the class rather than the word.)
    assert b'class="todo-assignees' not in res.body


def test_an_assignee_the_covering_does_not_account_for_is_still_shown(
    authenticated_testapp, dbsession, admin_user
):
    """Covering explains the team; it says nothing about anyone else on it."""
    alice = _user(dbsession, "alice")
    _user(dbsession, "bob")
    _team(dbsession, "kinder", assignees=[alice], supervisors=[admin_user])
    _todo_for(dbsession, "Feed the cat", {"kinder", "bob"}, owner=alice)
    today = datetime.date.today()
    _away(dbsession, alice, today, today)
    dbsession.flush()

    res = authenticated_testapp.get("/todos/groups", status=200)

    assert b"covering @kinder" in res.body
    assert b"@bob" in res.body
