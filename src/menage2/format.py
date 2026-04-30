import datetime as _dt
from datetime import datetime, timedelta, timezone

from babel.core import Locale
from babel.dates import get_timezone
from babel.support import Format
from pyramid.events import subscriber
from pyramid.interfaces import IBeforeRender
from sqlalchemy import func, or_, select

_TASKS_ROUTES = frozenset(
    {
        "list_todos",
        "list_todos_done",
        "list_todos_scheduled",
        "list_todos_hold",
        "add_todo",
        "edit_todo",
        "todos_done",
        "todos_hold",
        "todos_postpone",
        "todos_activate_all_on_hold",
        "todo_undo",
        "todos_activate_batch",
        "set_due_date",
        "parse_date_preview",
        "set_recurrence",
        "parse_recurrence_preview",
        "recurrence_history",
        "list_tags_json",
        "list_principals_json",
        "list_protocols",
        "new_protocol",
        "edit_protocol",
        "archive_protocol",
        "unarchive_protocol",
        "add_protocol_item",
        "update_protocol_item",
        "update_protocol_item_partial",
        "delete_protocol_item",
        "start_protocol_run",
        "show_protocol_run",
        "list_protocols_palette",
    }
)

_VALID_FILTER_MODES = frozenset({"all", "personal", "delegated_out", "delegated_in"})


def format_timedelta(td: timedelta):
    units = [
        ("hour", timedelta(seconds=60 * 60)),
        ("minute", timedelta(seconds=60)),
        ("second", timedelta(seconds=1)),
    ]
    result: list[int] = []
    for unit, unit_duration in units:
        if td > unit_duration:
            unit_count = int(td / unit_duration)
            result.append(unit_count)
            td = td - (unit_count * unit_duration)
        else:
            result.append(0)

    return ":".join(f"{d:02d}" for d in result)


def date_ago(d: _dt.date, today: _dt.date) -> str:
    days = (today - d).days
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


def humanize_ago(dt: datetime) -> str:
    seconds = int(
        (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
    )
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} min ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if seconds < 172800:
        return "yesterday"
    if seconds < 604800:
        return f"{seconds // 86400} days ago"
    if seconds < 2592000:
        w = seconds // 604800
        return f"{w} week{'s' if w != 1 else ''} ago"
    if seconds < 31536000:
        mo = seconds // 2592000
        return f"{mo} month{'s' if mo != 1 else ''} ago"
    y = seconds // 31536000
    return f"{y} year{'s' if y != 1 else ''} ago"


@subscriber(IBeforeRender)
def globals_factory(event):
    locale_name = event["request"].locale_name
    locale = Locale(locale_name)
    settings = event["request"].registry.settings
    tz_name = settings.get("menage.timezone", "Europe/Berlin")
    fmt = Format(locale, get_timezone(tz_name))
    event["format"] = fmt

    from menage2.models.config import ConfigItem
    from menage2.views.admin import BASE_NAME_KEY, DEFAULT_BASE_NAME

    request = event["request"]
    if hasattr(request, "dbsession"):
        item = request.dbsession.get(ConfigItem, BASE_NAME_KEY)
        event["base_name"] = item.value if item else DEFAULT_BASE_NAME
    else:
        event["base_name"] = DEFAULT_BASE_NAME

    def humanize_ago_with_weekday(dt: datetime) -> str:
        weekday = fmt.date(dt, format="EEEE")
        absolute = fmt.datetime(dt, format="medium")
        return f"{weekday}, {absolute}"

    def _recurrence_label(todo) -> str:
        """Short label for the ↻ badge — empty string when no rule."""
        if not getattr(todo, "recurrence", None):
            return ""
        from menage2.dateparse import label_recurrence
        from menage2.recurrence import rule_to_spec

        return label_recurrence(rule_to_spec(todo.recurrence))

    event["format_timedelta"] = format_timedelta
    event["date_ago"] = date_ago
    event["humanize_ago"] = humanize_ago
    event["absolute_with_weekday"] = humanize_ago_with_weekday
    event["_recurrence_label"] = _recurrence_label

    # Task sub-nav counts (active / on-hold / scheduled)
    request = event["request"]
    route_name = request.matched_route.name if request.matched_route else ""
    nav_task_counts = None
    if (
        route_name in _TASKS_ROUTES
        and request.identity is not None
        and hasattr(request, "dbsession")
    ):
        from menage2.models.todo import Todo, TodoStatus
        from menage2.principals import get_user_team_memberships, todo_matches_filter

        today = _dt.date.today()
        user = request.identity
        filter_mode = request.params.get("filter", "personal")
        if filter_mode not in _VALID_FILTER_MODES:
            filter_mode = "personal"
        db = request.dbsession
        db.flush()
        memberships = get_user_team_memberships(db, user)

        def _count(todos):
            return sum(
                1
                for t in todos
                if todo_matches_filter(t, user, memberships, filter_mode)
            )

        todos_active = (
            db.execute(
                select(Todo).where(
                    Todo.status == TodoStatus.todo,
                    or_(Todo.due_date.is_(None), Todo.due_date <= today),
                )
            )
            .scalars()
            .all()
        )
        todos_hold = (
            db.execute(select(Todo).where(Todo.status == TodoStatus.on_hold))
            .scalars()
            .all()
        )
        todos_sched = (
            db.execute(
                select(Todo).where(
                    Todo.status == TodoStatus.todo, Todo.due_date > today
                )
            )
            .scalars()
            .all()
        )
        nav_task_counts = {
            "active": _count(todos_active),
            "hold": _count(todos_hold),
            "scheduled": _count(todos_sched),
        }

    event["nav_task_counts"] = nav_task_counts
