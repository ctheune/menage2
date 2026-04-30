"""Principal resolution and todo/protocol visibility helpers.

A *principal* is any named entity that can be addressed with @name in a todo:
either a User (by username) or a Team (by name).  Both share a unique
namespace enforced at the application layer.

Visibility model
----------------
A todo is visible to user U if ANY of:
  - todo.owner_id == U.id
  - U.username in todo.assignees  (direct individual assignee)
  - a team name in todo.assignees where U is a member (any role)

Filter modes
------------
  "personal" — unowned (legacy), owned-and-not-delegated-away (or self is assignee),
               direct assignee, or assignee-role team member
  "all"      — owner, unowned, direct assignee, or any team member (assignee OR supervisor)
  "delegated_out"  — (owner AND has assignees AND NOT self-assignee AND NOT assignee-role team)
                     OR (NOT owner AND supervisor-role team member of an assigned team)
  "delegated_in"   — (direct assignee OR assignee-role team member) AND NOT owner

NOTE: Team expansion is done inline (one array-containment clause per team the
user belongs to).  Household teams are tiny so this is fine; avoids a join.
"""

from sqlalchemy import Text, cast, or_, select
from sqlalchemy.dialects.postgresql import ARRAY

from .models.team import Team, TeamMember
from .models.todo import Todo
from .models.user import User


def get_all_principals(dbsession) -> list[dict]:
    """Return sorted list of {name, type} dicts for all active users and teams."""
    users = (
        dbsession.execute(
            select(User.username).where(User.is_active == True)  # noqa: E712
        )
        .scalars()
        .all()
    )
    teams = dbsession.execute(select(Team.name)).scalars().all()
    result = [{"name": u, "type": "user"} for u in users]
    result += [{"name": t, "type": "team"} for t in teams]
    result.sort(key=lambda p: p["name"])
    return result


def get_user_team_memberships(dbsession, user) -> dict[str, str]:
    """Return {team_name: role} for every team the user belongs to."""
    rows = dbsession.execute(
        select(Team.name, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
    ).all()
    return {name: role for name, role in rows}


def _assignees_contains(name: str):
    """SQLAlchemy clause: Todo.assignees array contains the given name."""
    return Todo.assignees.contains(cast([name], ARRAY(Text)))


def _proto_assignees_contains(model, name: str):
    """SQLAlchemy clause: model.assignees array contains the given name."""
    return model.assignees.contains(cast([name], ARRAY(Text)))


def filter_todos_for_user(stmt, user, dbsession, filter_mode: str = "personal"):
    """Wrap a SELECT(Todo) statement with per-user visibility + filter_mode clauses.

    Args:
        stmt: A SQLAlchemy select() statement already selecting Todo rows.
        user: The authenticated User ORM object.
        dbsession: Active SQLAlchemy session.
        filter_mode: One of "personal", "all", "delegated_out", "delegated_in".
    """
    memberships = get_user_team_memberships(dbsession, user)

    # Clauses for every team the user belongs to (any role).
    team_assignee_clauses = [
        _assignees_contains(team_name) for team_name in memberships
    ]

    # Clauses only for assignee-role teams.
    assignee_role_team_clauses = [
        _assignees_contains(team_name)
        for team_name, role in memberships.items()
        if role == "assignee"
    ]

    # Clauses only for supervisor-role teams.
    supervisor_role_team_clauses = [
        _assignees_contains(team_name)
        for team_name, role in memberships.items()
        if role == "supervisor"
    ]

    is_owner = Todo.owner_id == user.id
    is_unowned = Todo.owner_id.is_(None)  # legacy: NULL = visible to all
    is_direct_assignee = _assignees_contains(user.username)
    has_assignees = Todo.assignees != cast([], ARRAY(Text))

    if filter_mode == "delegated_out":
        # Case 1: I own it and delegated it, but I'm not also an executor.
        # Build NOT-self-assignee: exclude direct assignee and assignee-role team membership.
        not_self_assignee = ~is_direct_assignee
        for team_clause in assignee_role_team_clauses:
            not_self_assignee = not_self_assignee & ~team_clause
        delegated_out_owner = is_owner & has_assignees & not_self_assignee
        # Case 2: I'm not the owner but I'm a supervisor of an assigned team.
        if supervisor_role_team_clauses:
            delegated_out_supervisor = ~is_owner & or_(*supervisor_role_team_clauses)
            return stmt.where(or_(delegated_out_owner, delegated_out_supervisor))
        return stmt.where(delegated_out_owner)

    if filter_mode == "delegated_in":
        # Items assigned to me (directly or as assignee-role team) that I don't own.
        delegated_in_clauses = [is_direct_assignee] + assignee_role_team_clauses
        return stmt.where(
            ~is_owner,
            or_(*delegated_in_clauses) if delegated_in_clauses else is_direct_assignee,
        )

    if filter_mode == "personal":
        # Owned todos that haven't been delegated away (or the owner is also an
        # assignee), plus todos directly assigned/team-assigned to this user.
        not_delegated_away = ~has_assignees | is_direct_assignee
        personal_clauses = [
            is_owner & not_delegated_away,
            is_unowned,
            is_direct_assignee,
        ] + assignee_role_team_clauses
        return stmt.where(or_(*personal_clauses))

    # "all" — all items the user can see: owner, unowned, direct assignee, any team member.
    responsible_clauses = [
        is_owner,
        is_unowned,
        is_direct_assignee,
    ] + team_assignee_clauses
    return stmt.where(or_(*responsible_clauses))


def filter_protocols_for_user(stmt, user, dbsession):
    """Wrap a SELECT(Protocol) statement with per-user visibility clauses.

    A protocol is visible if the user is the owner, a direct assignee, or a
    member (any role) of an assigned team.
    """
    from sqlalchemy import Text, cast, or_
    from sqlalchemy.dialects.postgresql import ARRAY

    from .models.protocol import Protocol

    if user is None:
        return stmt

    memberships = get_user_team_memberships(dbsession, user)

    def _contains(name: str):
        return Protocol.assignees.contains(cast([name], ARRAY(Text)))

    visible_clauses = [
        Protocol.owner_id == user.id,
        Protocol.owner_id.is_(None),
        _contains(user.username),
    ] + [_contains(team_name) for team_name in memberships]

    return stmt.where(or_(*visible_clauses))


def is_protocol_editor(user, protocol, dbsession) -> bool:
    """Return True if user may edit the protocol.

    Editors are: the owner, or a supervisor-role member of any assigned team.
    """
    if user is None:
        return False
    if user.id == protocol.owner_id:
        return True
    memberships = get_user_team_memberships(dbsession, user)
    for team_name, role in memberships.items():
        if role == "supervisor" and team_name in protocol.assignees:
            return True
    return False
