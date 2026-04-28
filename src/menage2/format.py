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
        from menage2.principals import filter_todos_for_user

        today = _dt.date.today()
        user = request.identity
        filter_mode = request.params.get("filter", "personal")
        if filter_mode not in _VALID_FILTER_MODES:
            filter_mode = "personal"
        db = request.dbsession
        db.flush()

        stmt_active = filter_todos_for_user(
            select(func.count())
            .select_from(Todo)
            .where(
                Todo.status == TodoStatus.todo,
                or_(Todo.due_date.is_(None), Todo.due_date <= today),
            ),
            user,
            db,
            filter_mode,
        )
        stmt_hold = filter_todos_for_user(
            select(func.count())
            .select_from(Todo)
            .where(Todo.status == TodoStatus.on_hold),
            user,
            db,
            filter_mode,
        )
        stmt_sched = filter_todos_for_user(
            select(func.count())
            .select_from(Todo)
            .where(Todo.status == TodoStatus.todo, Todo.due_date > today),
            user,
            db,
            filter_mode,
        )
        nav_task_counts = {
            "active": db.execute(stmt_active).scalar(),
            "hold": db.execute(stmt_hold).scalar(),
            "scheduled": db.execute(stmt_sched).scalar(),
        }

    event["nav_task_counts"] = nav_task_counts
