"""Integration tests for the teams / principals / visibility feature."""

import datetime

import pytest
from sqlalchemy import select

from menage2.models.protocol import Protocol
from menage2.models.team import Team, TeamMember
from menage2.models.todo import Todo, TodoStatus
from menage2.models.user import User
from menage2.principals import (
    get_all_principals,
    get_user_team_memberships,
    is_protocol_editor,
    protocol_visible_to_user,
    todo_matches_filter,
)
from menage2.views.todo import parse_todo_input


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _todo(dbsession, text="Test", tags=None, assignees=None, owner_id=None):
    t = Todo(
        text=text,
        tags=tags if tags is not None else set(),
        assignees=assignees if assignees is not None else set(),
        owner_id=owner_id,
        status=TodoStatus.todo,
        created_at=_now(),
    )
    dbsession.add(t)
    dbsession.flush()
    return t


# ---------------------------------------------------------------------------
# parse_todo_input — @mention extraction
# ---------------------------------------------------------------------------


def test_parse_todo_input_extracts_assignees():
    parsed = parse_todo_input("Buy milk @alice #shopping")
    assert parsed.assignees == {"alice"}
    assert parsed.tags == {"shopping"}
    assert parsed.text == "Buy milk"


def test_parse_todo_input_multiple_assignees():
    parsed = parse_todo_input("Fix bug @alice @bob")
    assert parsed.assignees == {"alice", "bob"}
    assert parsed.text == "Fix bug"


def test_parse_todo_input_no_assignees():
    parsed = parse_todo_input("Clean kitchen #home")
    assert parsed.assignees == set()
    assert parsed.text == "Clean kitchen"


def test_parse_todo_input_assignees_round_trip():
    raw = "Walk dog @alice ^2026-05-01 #outdoor"
    parsed = parse_todo_input(raw)
    assert parsed.assignees == {"alice"}
    assert parsed.tags == {"outdoor"}
    assert parsed.text == "Walk dog"
    assert parsed.due_date is not None


# ---------------------------------------------------------------------------
# Admin team CRUD
# ---------------------------------------------------------------------------


def test_create_team_requires_admin(user_testapp):
    res = user_testapp.post("/admin/teams/new", {"name": "ops"}, status=403)
    assert res.status_int == 403


def test_create_team_success(authenticated_testapp, dbsession):
    res = authenticated_testapp.post(
        "/admin/teams/new", {"name": "cleaning-crew"}, status=303
    )
    assert "admin/teams" in res.location
    team = dbsession.execute(
        select(Team).where(Team.name == "cleaning-crew")
    ).scalar_one_or_none()
    assert team is not None


def test_team_name_conflicts_with_username(authenticated_testapp, admin_user):
    res = authenticated_testapp.post(
        "/admin/teams/new", {"name": admin_user.username}, status=200
    )
    assert b"taken" in res.body.lower()


def test_team_name_conflicts_with_existing_team(authenticated_testapp, dbsession):
    authenticated_testapp.post("/admin/teams/new", {"name": "alpha"}, status=303)
    res = authenticated_testapp.post("/admin/teams/new", {"name": "alpha"}, status=200)
    assert b"taken" in res.body.lower()


def test_user_creation_conflicts_with_team_name(authenticated_testapp, dbsession):
    authenticated_testapp.post("/admin/teams/new", {"name": "ops"}, status=303)
    res = authenticated_testapp.post(
        "/admin/users/new",
        {
            "username": "ops",
            "real_name": "Ops User",
            "email": "ops@example.com",
            "password": "pw",
        },
        status=200,
    )
    assert b"team" in res.body.lower()


def test_add_remove_team_member(
    authenticated_testapp, dbsession, admin_user, regular_user
):
    authenticated_testapp.post("/admin/teams/new", {"name": "testers"}, status=303)
    team = dbsession.execute(select(Team).where(Team.name == "testers")).scalar_one()
    authenticated_testapp.post(
        f"/admin/teams/{team.id}/members",
        {"user_id": str(regular_user.id), "role": "assignee"},
        status=303,
    )
    dbsession.expire_all()
    member = dbsession.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == regular_user.id
        )
    ).scalar_one_or_none()
    assert member is not None
    assert member.role == "assignee"
    member_id = member.id
    authenticated_testapp.post(
        f"/admin/teams/{team.id}/members/{member_id}/remove", status=303
    )
    dbsession.expire_all()
    assert (
        dbsession.execute(
            select(TeamMember).where(TeamMember.id == member_id)
        ).scalar_one_or_none()
        is None
    )


# ---------------------------------------------------------------------------
# Principals JSON endpoint
# ---------------------------------------------------------------------------


def test_principals_json_returns_users_and_teams(
    authenticated_testapp, admin_user, dbsession
):
    authenticated_testapp.post("/admin/teams/new", {"name": "alpha"}, status=303)
    res = authenticated_testapp.get("/todos/principals.json", status=200)
    names = [p["name"] for p in res.json]
    assert admin_user.username in names
    assert "alpha" in names


def test_principals_json_excludes_inactive_users(
    authenticated_testapp, dbsession, regular_user
):
    regular_user.is_active = False
    dbsession.flush()
    res = authenticated_testapp.get("/todos/principals.json", status=200)
    names = [p["name"] for p in res.json]
    assert regular_user.username not in names


# ---------------------------------------------------------------------------
# add_todo sets owner_id
# ---------------------------------------------------------------------------


def test_add_todo_sets_owner_id(authenticated_testapp, admin_user, dbsession):
    authenticated_testapp.post(
        "/todos/add", {"text": "Owner test", "next": "/todos"}, status=303
    )
    todo = dbsession.execute(
        select(Todo).where(Todo.text == "Owner test")
    ).scalar_one_or_none()
    assert todo is not None
    assert todo.owner_id == admin_user.id


# ---------------------------------------------------------------------------
# Visibility helpers — pure-Python predicate tests (no HTTP, no extra DB round-trips)
# ---------------------------------------------------------------------------


def _m(dbsession, user):
    """Shorthand: load team memberships for user."""
    return get_user_team_memberships(dbsession, user)


def test_visibility_all_includes_owned(dbsession, admin_user):
    t = _todo(dbsession, "Mine", owner_id=admin_user.id)
    assert todo_matches_filter(t, admin_user, _m(dbsession, admin_user), "all")


def test_visibility_all_includes_direct_assignee(dbsession, admin_user, regular_user):
    t = _todo(
        dbsession,
        "Delegated",
        owner_id=admin_user.id,
        assignees={regular_user.username},
    )
    assert todo_matches_filter(t, regular_user, _m(dbsession, regular_user), "all")


def test_visibility_all_excludes_other_users_unassigned(
    dbsession, admin_user, regular_user
):
    t = _todo(dbsession, "Not mine", owner_id=admin_user.id)
    assert not todo_matches_filter(t, regular_user, _m(dbsession, regular_user), "all")


def test_visibility_personal_excludes_delegated_out_without_self(
    dbsession, admin_user, regular_user
):
    # Owned + assigned to someone else (not me) must NOT appear in personal.
    t = _todo(
        dbsession,
        "Delegated out",
        owner_id=admin_user.id,
        assignees={regular_user.username},
    )
    assert not todo_matches_filter(t, admin_user, _m(dbsession, admin_user), "personal")


def test_visibility_personal_includes_owned_self_assigned(
    dbsession, admin_user, regular_user
):
    # Owned + I am one of the assignees → still personal.
    t = _todo(
        dbsession,
        "Self-assigned",
        owner_id=admin_user.id,
        assignees={admin_user.username, regular_user.username},
    )
    assert todo_matches_filter(t, admin_user, _m(dbsession, admin_user), "personal")


def test_visibility_all_includes_delegated_out(dbsession, admin_user, regular_user):
    t = _todo(
        dbsession,
        "Delegated out all",
        owner_id=admin_user.id,
        assignees={regular_user.username},
    )
    assert todo_matches_filter(t, admin_user, _m(dbsession, admin_user), "all")


def test_visibility_personal_includes_own_unassigned(dbsession, admin_user):
    t = _todo(dbsession, "Personal", owner_id=admin_user.id)
    assert todo_matches_filter(t, admin_user, _m(dbsession, admin_user), "personal")


def test_visibility_personal_includes_team_assignee(
    dbsession, admin_user, regular_user
):
    team = Team(name="haushalt", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(TeamMember(team_id=team.id, user_id=regular_user.id, role="assignee"))
    dbsession.flush()
    t = _todo(
        dbsession, "Haushalt task", owner_id=admin_user.id, assignees={"haushalt"}
    )
    assert todo_matches_filter(t, regular_user, _m(dbsession, regular_user), "personal")


def test_visibility_delegated_out(dbsession, admin_user, regular_user):
    t = _todo(
        dbsession,
        "Delegated",
        owner_id=admin_user.id,
        assignees={regular_user.username},
    )
    assert todo_matches_filter(
        t, admin_user, _m(dbsession, admin_user), "delegated_out"
    )


def test_visibility_delegated_in_includes_direct_assignee(
    dbsession, admin_user, regular_user
):
    t = _todo(
        dbsession,
        "Delegated in",
        owner_id=admin_user.id,
        assignees={regular_user.username},
    )
    assert todo_matches_filter(
        t, regular_user, _m(dbsession, regular_user), "delegated_in"
    )


def test_visibility_team_assignee_role_in_all(dbsession, admin_user, regular_user):
    team = Team(name="myteam", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(TeamMember(team_id=team.id, user_id=regular_user.id, role="assignee"))
    dbsession.flush()
    t = _todo(dbsession, "Team task", owner_id=admin_user.id, assignees={"myteam"})
    assert todo_matches_filter(t, regular_user, _m(dbsession, regular_user), "all")


def test_visibility_supervisor_team_included_in_all(
    dbsession, admin_user, regular_user
):
    team = Team(name="supervisors", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(
        TeamMember(team_id=team.id, user_id=regular_user.id, role="supervisor")
    )
    dbsession.flush()
    t = _todo(
        dbsession, "Supervisor task", owner_id=admin_user.id, assignees={"supervisors"}
    )
    assert todo_matches_filter(t, regular_user, _m(dbsession, regular_user), "all")


def test_visibility_supervisor_team_excluded_from_delegated_in(
    dbsession, admin_user, regular_user
):
    team = Team(name="watchers", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(
        TeamMember(team_id=team.id, user_id=regular_user.id, role="supervisor")
    )
    dbsession.flush()
    t = _todo(dbsession, "Watch task", owner_id=admin_user.id, assignees={"watchers"})
    assert not todo_matches_filter(
        t, regular_user, _m(dbsession, regular_user), "delegated_in"
    )


def test_visibility_delegated_out_excludes_direct_assignee_owner(dbsession, admin_user):
    t = _todo(
        dbsession,
        "Self-delegated",
        owner_id=admin_user.id,
        assignees={admin_user.username},
    )
    assert not todo_matches_filter(
        t, admin_user, _m(dbsession, admin_user), "delegated_out"
    )


def test_visibility_delegated_out_excludes_assignee_role_team_owner(
    dbsession, admin_user
):
    team = Team(name="myteam", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(TeamMember(team_id=team.id, user_id=admin_user.id, role="assignee"))
    dbsession.flush()
    t = _todo(dbsession, "Self via team", owner_id=admin_user.id, assignees={"myteam"})
    assert not todo_matches_filter(
        t, admin_user, _m(dbsession, admin_user), "delegated_out"
    )


def test_visibility_delegated_out_supervisor_non_owner(
    dbsession, admin_user, regular_user
):
    team = Team(name="supervised", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(
        TeamMember(team_id=team.id, user_id=regular_user.id, role="supervisor")
    )
    dbsession.flush()
    t = _todo(dbsession, "Team task", owner_id=admin_user.id, assignees={"supervised"})
    assert todo_matches_filter(
        t, regular_user, _m(dbsession, regular_user), "delegated_out"
    )


def test_visibility_delegated_in_includes_assignee_role_team(
    dbsession, admin_user, regular_user
):
    team = Team(name="doers", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(TeamMember(team_id=team.id, user_id=regular_user.id, role="assignee"))
    dbsession.flush()
    t = _todo(dbsession, "Team work", owner_id=admin_user.id, assignees={"doers"})
    assert todo_matches_filter(
        t, regular_user, _m(dbsession, regular_user), "delegated_in"
    )


def test_get_user_team_memberships(dbsession, regular_user):
    team = Team(name="alpha", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(TeamMember(team_id=team.id, user_id=regular_user.id, role="assignee"))
    dbsession.flush()
    memberships = get_user_team_memberships(dbsession, regular_user)
    assert memberships == {"alpha": "assignee"}


# ---------------------------------------------------------------------------
# Protocol visibility
# ---------------------------------------------------------------------------


def test_protocol_assigned_to_team_visible_to_team_assignee(
    user_testapp, dbsession, admin_user, regular_user
):
    """A protocol with a team in assignees must appear for team members."""
    team = Team(name="haushalt", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(TeamMember(team_id=team.id, user_id=regular_user.id, role="assignee"))
    p = Protocol(
        title="Team protocol",
        owner_id=admin_user.id,
        assignees={"haushalt"},
        created_at=_now(),
    )
    dbsession.add(p)
    dbsession.flush()

    res = user_testapp.get("/protocols", status=200)
    assert b"Team protocol" in res.body


def test_protocol_assignee_cannot_edit_or_archive(
    user_testapp, dbsession, admin_user, regular_user
):
    """Non-owner assignees must get 403 on all mutating protocol endpoints."""
    from menage2.models.protocol import ProtocolItem

    p = Protocol(
        title="Owner-only protocol",
        owner_id=admin_user.id,
        assignees={regular_user.username},
        created_at=_now(),
    )
    dbsession.add(p)
    dbsession.flush()
    item = ProtocolItem(protocol_id=p.id, position=0, text="Do thing")
    dbsession.add(item)
    dbsession.flush()

    # View is allowed.
    user_testapp.get(f"/protocols/{p.id}/edit", status=200)

    # All mutating endpoints return 403.
    user_testapp.post(f"/protocols/{p.id}/edit", {"title": "Hacked"}, status=403)
    user_testapp.post(f"/protocols/{p.id}/archive", status=403)
    user_testapp.post(f"/protocols/{p.id}/items", {"text": "injected"}, status=403)
    user_testapp.post(
        f"/protocols/{p.id}/items/{item.id}",
        {"text": "changed"},
        status=403,
    )
    user_testapp.post(
        f"/protocols/{p.id}/items/{item.id}/partial",
        {"text": "changed"},
        status=403,
    )
    user_testapp.post(f"/protocols/{p.id}/items/{item.id}/delete", status=403)


def test_protocol_assignee_can_start_run(
    user_testapp, dbsession, admin_user, regular_user
):
    """Non-owner assignees are allowed to start a run."""
    p = Protocol(
        title="Runnable protocol",
        owner_id=admin_user.id,
        assignees={regular_user.username},
        created_at=_now(),
    )
    dbsession.add(p)
    dbsession.flush()
    from menage2.models.protocol import ProtocolRun

    user_testapp.post(f"/protocols/{p.id}/start", status=303)
    assert (
        dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Protocol editor: supervisor can edit, assignee-role cannot
# ---------------------------------------------------------------------------


def test_protocol_supervisor_can_edit(
    user_testapp, dbsession, admin_user, regular_user
):
    """Supervisor-role team members may edit the protocol."""
    from menage2.models.protocol import ProtocolItem

    team = Team(name="supervisors", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(
        TeamMember(team_id=team.id, user_id=regular_user.id, role="supervisor")
    )
    p = Protocol(
        title="Supervised protocol",
        owner_id=admin_user.id,
        assignees={"supervisors"},
        created_at=_now(),
    )
    dbsession.add(p)
    dbsession.flush()
    item = ProtocolItem(protocol_id=p.id, position=1, text="Step one")
    dbsession.add(item)
    dbsession.flush()

    user_testapp.get(f"/protocols/{p.id}/edit", status=200)
    user_testapp.post(f"/protocols/{p.id}/archive", status=303)
    p.archived_at = None
    dbsession.flush()
    user_testapp.post(f"/protocols/{p.id}/items", {"text": "New step"}, status=303)
    user_testapp.post(
        f"/protocols/{p.id}/items/{item.id}", {"text": "Changed"}, status=303
    )


def test_protocol_assignee_role_cannot_edit(
    user_testapp, dbsession, admin_user, regular_user
):
    """Assignee-role team members may NOT edit the protocol."""
    from menage2.models.protocol import ProtocolItem

    team = Team(name="doers", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(TeamMember(team_id=team.id, user_id=regular_user.id, role="assignee"))
    p = Protocol(
        title="Doers protocol",
        owner_id=admin_user.id,
        assignees={"doers"},
        created_at=_now(),
    )
    dbsession.add(p)
    dbsession.flush()
    item = ProtocolItem(protocol_id=p.id, position=1, text="A step")
    dbsession.add(item)
    dbsession.flush()

    user_testapp.get(f"/protocols/{p.id}/edit", status=200)
    user_testapp.post(f"/protocols/{p.id}/archive", status=403)
    user_testapp.post(f"/protocols/{p.id}/items", {"text": "injected"}, status=403)
    user_testapp.post(
        f"/protocols/{p.id}/items/{item.id}", {"text": "changed"}, status=403
    )


# ---------------------------------------------------------------------------
# filter_protocols_for_user unit tests
# ---------------------------------------------------------------------------


def test_filter_protocols_owner_visible(dbsession, admin_user):
    from menage2.models.protocol import Protocol

    p = Protocol(title="Mine", owner_id=admin_user.id, created_at=_now())
    dbsession.add(p)
    dbsession.flush()
    assert protocol_visible_to_user(p, admin_user, _m(dbsession, admin_user))


def test_filter_protocols_direct_assignee_visible(dbsession, admin_user, regular_user):
    from menage2.models.protocol import Protocol

    p = Protocol(
        title="Assigned",
        owner_id=admin_user.id,
        assignees={regular_user.username},
        created_at=_now(),
    )
    dbsession.add(p)
    dbsession.flush()
    assert protocol_visible_to_user(p, regular_user, _m(dbsession, regular_user))


def test_filter_protocols_supervisor_team_visible(dbsession, admin_user, regular_user):
    from menage2.models.protocol import Protocol

    team = Team(name="oversight", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(
        TeamMember(team_id=team.id, user_id=regular_user.id, role="supervisor")
    )
    p = Protocol(
        title="Overseen",
        owner_id=admin_user.id,
        assignees={"oversight"},
        created_at=_now(),
    )
    dbsession.add(p)
    dbsession.flush()
    assert protocol_visible_to_user(p, regular_user, _m(dbsession, regular_user))


def test_filter_protocols_non_member_invisible(dbsession, admin_user, regular_user):
    from menage2.models.protocol import Protocol

    p = Protocol(title="Private", owner_id=admin_user.id, created_at=_now())
    dbsession.add(p)
    dbsession.flush()
    assert not protocol_visible_to_user(p, regular_user, _m(dbsession, regular_user))


# ---------------------------------------------------------------------------
# is_protocol_editor unit tests
# ---------------------------------------------------------------------------


def test_is_protocol_editor_owner(dbsession, admin_user):
    from menage2.models.protocol import Protocol

    p = Protocol(title="P", owner_id=admin_user.id, created_at=_now())
    dbsession.add(p)
    dbsession.flush()
    assert is_protocol_editor(admin_user, p, _m(dbsession, admin_user)) is True


def test_is_protocol_editor_supervisor(dbsession, admin_user, regular_user):
    from menage2.models.protocol import Protocol

    team = Team(name="mgrs", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(
        TeamMember(team_id=team.id, user_id=regular_user.id, role="supervisor")
    )
    p = Protocol(
        title="P", owner_id=admin_user.id, assignees={"mgrs"}, created_at=_now()
    )
    dbsession.add(p)
    dbsession.flush()
    assert is_protocol_editor(regular_user, p, _m(dbsession, regular_user)) is True


def test_is_protocol_editor_assignee_role_not_editor(
    dbsession, admin_user, regular_user
):
    from menage2.models.protocol import Protocol

    team = Team(name="workers", created_at=_now())
    dbsession.add(team)
    dbsession.flush()
    dbsession.add(TeamMember(team_id=team.id, user_id=regular_user.id, role="assignee"))
    p = Protocol(
        title="P", owner_id=admin_user.id, assignees={"workers"}, created_at=_now()
    )
    dbsession.add(p)
    dbsession.flush()
    assert is_protocol_editor(regular_user, p, _m(dbsession, regular_user)) is False
