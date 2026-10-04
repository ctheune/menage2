"""Principal resolution and todo/protocol visibility helpers.

A *principal* is any named entity that can be addressed with @name in a todo:
either a User or a Team.  Both own a row in `principals`, which is where the
name lives and where the shared namespace is enforced by a unique index.

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

import sqlalchemy
import sqlalchemy.orm
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from .models.principal import Principal
from .models.team import TeamMember
from .models.user import Absence, User


def get_all_principals(dbsession) -> list[dict]:
    """Return sorted list of {name, type} dicts for all active users and teams.

    One query since both live in `principals`; a deactivated account is left
    out, which is why the join to `users` is there at all.
    """
    rows = dbsession.execute(
        select(Principal.name, Principal.kind)
        .outerjoin(User, User.id == Principal.user_id)
        .where((Principal.kind == "team") | (User.is_active == True))
        .order_by(Principal.name)
    ).all()
    return [{"name": name, "type": kind} for name, kind in rows]


def unknown_principals(dbsession, names) -> set[str]:
    """Which of `names` name no user and no team.

    Checked in the views so that somebody who typed `@nobdoy` is told
    about it; writing the assignment refuses too, but by then the request
    is failing rather than answering.
    """
    names = set(names or ())
    if not names:
        return set()
    known = set(
        dbsession.execute(
            select(Principal.name).where(Principal.name.in_(names))
        ).scalars()
    )
    return names - known


def get_user_team_memberships(dbsession, user) -> dict[str, str]:
    """Return {team_name: role} for every team the user belongs to."""
    rows = dbsession.execute(
        select(Principal.name, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Principal.team_id)
        .where(TeamMember.user_id == user.id)
    ).all()
    return {name: role for name, role in rows}


def absent_usernames(dbsession, day) -> set[str]:
    """Everybody who is away on `day`.

    A deactivated account counts as away and stays that way: somebody who
    has left is not coming back on Monday, and their team's work should not
    wait for them.

    The stretch each absence covers is worked out in Python rather than in
    the query: a Monday start reaches back over the weekend before it and a
    Friday end reaches forward over the one after, and that rule belongs
    next to the dates it is about. The query narrows to absences that could
    possibly reach `day` first, so only a handful are ever looked at.
    """
    import datetime

    away = set(
        dbsession.execute(
            select(Principal.name)
            .join(User, User.id == Principal.user_id)
            .where(User.is_active == False)
        )
        .scalars()
        .all()
    )

    reach = datetime.timedelta(days=2)
    rows = dbsession.execute(
        select(Absence, Principal.name)
        .join(Principal, Principal.user_id == Absence.user_id)
        .where(Absence.starts_on <= day + reach, Absence.ends_on >= day - reach)
    ).all()
    away.update(username for absence, username in rows if absence.covers(day))
    return away


def uncovered_teams(dbsession, user, memberships: dict[str, str], day) -> set[str]:
    """Teams `user` supervises whose assignees are, today, all away.

    A team with nobody assigned to it is not covered by this: "everyone is
    away" should mean somebody was there to go away in the first place, and
    an empty team is a setup left half done rather than a holiday.
    """
    supervised = {name for name, role in memberships.items() if role == "supervisor"}
    if not supervised:
        return set()

    team = sqlalchemy.orm.aliased(Principal)
    member = sqlalchemy.orm.aliased(Principal)
    rows = dbsession.execute(
        select(team.name, member.name)
        .join(TeamMember, TeamMember.team_id == team.team_id)
        .join(member, member.user_id == TeamMember.user_id)
        .where(team.name.in_(supervised), TeamMember.role == "assignee")
    ).all()

    assignees: dict[str, set[str]] = {}
    for team_name, username in rows:
        assignees.setdefault(team_name, set()).add(username)

    away = absent_usernames(dbsession, day)
    return {team for team, members in assignees.items() if members and members <= away}


def todo_matches_filter(
    todo,
    user,
    memberships: dict[str, str],
    filter_mode: str,
    covering: set[str] = frozenset(),
) -> bool:
    """Return True if *todo* matches *filter_mode* for *user*.

    Args:
        todo: A Todo ORM object (assignees is a set of principal names).
        user: The authenticated User ORM object.
        memberships: {team_name: role} from get_user_team_memberships().
        filter_mode: One of "personal", "all", "delegated_out", "delegated_in".
        covering: team names from uncovered_teams() — teams this user
            supervises whose assignees are all away today. Their work counts
            as the supervisor's own until somebody is back.
    """
    assignee_teams = {tn for tn, role in memberships.items() if role == "assignee"}
    supervisor_teams = {tn for tn, role in memberships.items() if role == "supervisor"}

    is_owner = todo.owner == user
    is_unowned = todo.owner is None
    is_direct_assignee = user.username in todo.assignees
    has_assignees = bool(todo.assignees)
    in_assignee_team = bool(assignee_teams & todo.assignees)
    in_supervisor_team = bool(supervisor_teams & todo.assignees)
    covers_for_team = bool(covering & todo.assignees)

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
            or covers_for_team
        )

    # "all" — everything the user can see
    return (
        is_owner
        or is_unowned
        or is_direct_assignee
        or in_assignee_team
        or in_supervisor_team
    )


def item_visible_to_user(item, user, memberships: dict[str, str]) -> bool:
    """Whether `user` may see `item`, whatever kind it is.

    Files and links hang off any item now, so the gate that used to ask
    "can you see this todo" has to answer for five kinds. Each is referred
    to whoever already decides it: a task and a run answer to the task
    filters, a checklist and its lines to the checklist they belong to, and
    an ingredient to nothing -- the recipe book has no owner and everybody
    logged in cooks from it.
    """
    from .models.protocol import ProtocolItem, ProtocolRunItem

    if user is None:
        return False
    if item.kind in ("todo", "protocol_run"):
        return todo_matches_filter(item, user, memberships, "all")
    if item.kind == "protocol":
        return protocol_visible_to_user(item, user, memberships)
    if isinstance(item, ProtocolItem):
        return protocol_visible_to_user(item.protocol, user, memberships)
    if isinstance(item, ProtocolRunItem):
        run = item.run
        return run is not None and protocol_visible_to_user(
            run.protocol, user, memberships
        )
    # An unrecognised kind is not something to guess about.
    return item.kind == "ingredient"


def _principal_ids(dbsession, names) -> list[int]:
    names = set(names or ())
    if not names:
        return []
    return list(
        dbsession.execute(
            select(Principal.id).where(Principal.name.in_(names))
        ).scalars()
    )


def visible_items(
    dbsession,
    user,
    memberships: dict[str, str],
    filter_mode: str,
    covering: set[str] | None = None,
):
    """`todo_matches_filter` as a WHERE clause over Item.

    The same seven facts, composed the same four ways -- the docstring at
    the top of this module is the specification for both. Asking the
    database means the list stops loading every task in order to throw most
    of them away, and the counts on the filter tabs stop doing it four
    times per page.

    `todo_matches_filter` stays for the one-row question, where building a
    query would be the slower answer. A test asserts the two agree.
    """
    if covering is None:
        covering = set()
    from .models.assignee import item_assignees
    from .models.item import Item

    def assigned_to(ids) -> ColumnElement[bool]:
        if not ids:
            return sqlalchemy.false()
        return exists(
            select(1).where(
                item_assignees.c.item_id == Item.id,
                item_assignees.c.principal_id.in_(ids),
            )
        )

    def certain(expression) -> ColumnElement[bool]:
        """NULL is not true. An unowned item is not owned by somebody else."""
        return func.coalesce(expression, sqlalchemy.false())

    assignee_teams = {tn for tn, role in memberships.items() if role == "assignee"}
    supervisor_teams = {tn for tn, role in memberships.items() if role == "supervisor"}

    is_owner = certain(Item.owner_id == user.id)
    is_unowned = Item.owner_id.is_(None)
    is_direct_assignee = assigned_to(_principal_ids(dbsession, {user.username}))
    has_assignees = exists(select(1).where(item_assignees.c.item_id == Item.id))
    in_assignee_team = assigned_to(_principal_ids(dbsession, assignee_teams))
    in_supervisor_team = assigned_to(_principal_ids(dbsession, supervisor_teams))
    covers_for_team = assigned_to(_principal_ids(dbsession, covering))

    if filter_mode == "delegated_out":
        return or_(
            and_(
                is_owner,
                has_assignees,
                ~is_direct_assignee,
                ~in_assignee_team,
            ),
            and_(~is_owner, in_supervisor_team),
        )

    if filter_mode == "delegated_in":
        return and_(~is_owner, or_(is_direct_assignee, in_assignee_team))

    if filter_mode == "personal":
        return or_(
            and_(is_owner, or_(~has_assignees, is_direct_assignee)),
            is_unowned,
            is_direct_assignee,
            in_assignee_team,
            covers_for_team,
        )

    return or_(
        is_owner,
        is_unowned,
        is_direct_assignee,
        in_assignee_team,
        in_supervisor_team,
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
