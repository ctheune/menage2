"""Recording that somebody is away, and who picks up their team's work."""

import datetime

import pytest

from menage2.models.user import Absence, User
from menage2.principals import absent_usernames

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


def test_the_weekend_rule_reaches_the_query_too(dbsession):
    """The stretch is widened in Python, so the query has to look wider."""
    alice = _user(dbsession, "alice")
    _away(dbsession, alice, MONDAY, FRIDAY)

    assert absent_usernames(dbsession, SATURDAY_BEFORE) == {"alice"}
    assert absent_usernames(dbsession, SUNDAY_AFTER) == {"alice"}
    assert absent_usernames(dbsession, FRIDAY_BEFORE) == set()
    assert absent_usernames(dbsession, MONDAY_AFTER) == set()


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
