"""Principal resolution and todo/protocol visibility helpers.

A *principal* is any named entity that can be addressed with @name in a todo:
either a User (by username) or a Team (by name).  Both share a unique
namespace enforced at the application layer.

Filter modes (todos)
--------------------
  personal     — I need to act on: owner (not delegated away, or I am also assignee),
                 direct assignee, assignee-role team member, or unowned legacy
  all          — I can see: owner, direct assignee, any team member (any role), unowned
  delegated_out — (I own + has assignees + not self-assignee + not assignee-role team)
                  OR (I supervise an assigned team and do NOT own it)
  delegated_in — I need to act on but don't own: direct assignee or assignee-role team

Protocol rules
--------------
  visible — owner, direct assignee, or any team member (any role)
  editor  — owner, or supervisor-role member of an assigned team

NOTE: Team expansion uses Python set intersection on memberships — no inline SQL.
"""

from sqlalchemy import select

from .models.team import Team, TeamMember
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


def todo_matches_filter(
    todo, user, memberships: dict[str, str], filter_mode: str
) -> bool:
    """Return True if *todo* matches *filter_mode* for *user*.

    Args:
        todo: A Todo ORM object (assignees is a set of principal names).
        user: The authenticated User ORM object.
        memberships: {team_name: role} from get_user_team_memberships().
        filter_mode: One of "personal", "all", "delegated_out", "delegated_in".
    """
    assignee_teams = {tn for tn, role in memberships.items() if role == "assignee"}
    supervisor_teams = {tn for tn, role in memberships.items() if role == "supervisor"}

    is_owner = todo.owner == user
    is_unowned = todo.owner is None
    is_direct_assignee = user.username in todo.assignees
    has_assignees = bool(todo.assignees)
    in_assignee_team = bool(assignee_teams & todo.assignees)
    in_supervisor_team = bool(supervisor_teams & todo.assignees)

    if filter_mode == "delegated_out":
        owner_delegated = (
            is_owner
            and has_assignees
            and not is_direct_assignee
            and not in_assignee_team
        )
        supervisor_watching = not is_owner and in_supervisor_team
        return owner_delegated or supervisor_watching

    if filter_mode == "delegated_in":
        return not is_owner and (is_direct_assignee or in_assignee_team)

    if filter_mode == "personal":
        not_delegated_away = not has_assignees or is_direct_assignee
        return (
            (is_owner and not_delegated_away)
            or is_unowned
            or is_direct_assignee
            or in_assignee_team
        )

    # "all" — everything the user can see
    return (
        is_owner
        or is_unowned
        or is_direct_assignee
        or in_assignee_team
        or in_supervisor_team
    )


def protocol_visible_to_user(protocol, user, memberships: dict[str, str]) -> bool:
    """Return True if *user* may see *protocol*."""
    if protocol.owner == user:
        return True
    if protocol.owner is None:
        return True
    if user.username in protocol.assignees:
        return True
    return bool(set(memberships) & protocol.assignees)


def is_protocol_editor(user, protocol, memberships: dict[str, str]) -> bool:
    """Return True if *user* may edit *protocol* (owner or supervisor of assigned team)."""
    if user is None:
        return False
    if protocol.owner == user:
        return True
    supervisor_teams = {tn for tn, role in memberships.items() if role == "supervisor"}
    return bool(supervisor_teams & protocol.assignees)
