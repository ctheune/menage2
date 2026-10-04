import json
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from markupsafe import Markup
from pyramid.events import BeforeRender, subscriber
from pyramid.renderers import render
from pyramid.request import Request

if TYPE_CHECKING:
    from menage2.schemas import UndoEntry


class Seen:
    def __init__(self):
        self.seen = set()

    def __contains__(self, obj):
        result = obj in self.seen
        self.seen.add(obj)
        return result


class HXTrigger:
    def __init__(self, response):
        self.response = response
        self.data = {}

    def __bool__(self):
        return bool(self.data)

    def undo(self, entries: list["UndoEntry"], texts: list[str], action: str):
        """Offer to put `entries` back the way they were.

        Each entry is a snapshot taken before the change — id, status and due
        date — so one mechanism covers completing, holding, postponing and
        reactivating, and a batch spanning several previous states undoes
        correctly item by item.

        The snapshot travels as a JSON string: it ends up in a hidden form
        field, so it has to be a string by the time the client sees it.
        """
        label = texts[0] if len(texts) == 1 else f"{len(texts)} items"
        self(
            "showUndoToast",
            {
                "entries": json.dumps([e.model_dump(mode="json") for e in entries]),
                "label": label,
                "action": action,
            },
        )

    def __call__(self, key, value=None):
        assert key not in self.data
        self.data[key] = value
        self.response.headers["HX-Trigger"] = str(self)

    def __str__(self):
        return json.dumps(self.data)


@dataclass
class NavItem:
    title: str
    route_name: str = ""

    icon: str = ""
    css_class: str = ""
    partial: str = "nav_link"
    _query: dict[str, str] = field(default_factory=dict)

    view_condition: Callable[[Request], bool] = lambda r: r.identity is not None

    children: Sequence["NavItem"] = ()

    def bind(self, request: Request) -> "BoundNavItem":
        bound = BoundNavItem(
            self.title,
            route_name=self.route_name,
            icon=self.icon,
            css_class=self.css_class,
            _query=dict(self._query),
            partial=self.partial,
            view_condition=self.view_condition,
            children=[child.bind(request) for child in self.children],
        )
        bound.request = request
        return bound


class BoundNavItem(NavItem):
    request: Request
    children: Sequence["BoundNavItem"] = ()  # pyright: ignore[reportIncompatibleVariableOverride]

    def walk(self) -> "Generator[BoundNavItem]":
        yield self
        yield from self.children

    @property
    def focused(self) -> bool:
        return self.request.url == self.url

    @property
    def active(self) -> bool:
        if self.focused:
            return True
        return any(child.active for child in self.children)

    @property
    def url(self):
        if not self.route_name:
            return ""
        return self.request.route_url(self.route_name, _query=self._query)

    def __iter__(self):
        return iter([c for c in self.children if c.visible])

    @property
    def visible(self):
        return self.view_condition(self.request)

    def render(self):
        return self.request.partials[self.partial](link=self)


def navigation_view(view, info):
    options = info.options.get("navigation", {})

    def wrapper(context, request):
        request.navigation = Navigation(request, options)
        return view(context, request)

    return wrapper


navigation_view.options = ("navigation",)  # pyright: ignore[reportFunctionMemberAccess]


def includeme(config):
    config.add_view_deriver(navigation_view)


class Navigation:
    """A collection of navigation roots - kind of like a forest."""

    roots: ClassVar[dict[str, NavItem]] = {
        "main": NavItem(
            "Happy Valley",
            route_name="home",
            children=[
                NavItem(
                    "Food",
                    route_name="list_weeks",
                    children=[
                        NavItem("Meal Planner", "list_weeks"),
                        NavItem("Recipes", "list_recipes"),
                        NavItem("Ingredients", "list_ingredients"),
                    ],
                ),
                NavItem(
                    "TODO",
                    route_name="list_todos",
                    children=[
                        NavItem(
                            "My Tasks",
                            "list_todos",
                            _query={"filter": "personal"},
                        ),
                        NavItem(
                            "Assigned",
                            "list_todos",
                            _query={"filter": "delegated_in"},
                        ),
                        NavItem(
                            "Delegated",
                            "list_todos",
                            _query={"filter": "delegated_out"},
                        ),
                        NavItem(
                            "All",
                            "list_todos",
                            _query={"filter": "all"},
                        ),
                        NavItem("Protocols", "list_protocols"),
                    ],
                ),
                NavItem(
                    "Operations",
                    "admin_users",
                    children=[
                        NavItem("Crew", "admin_users"),
                        NavItem("Departments", "admin_teams"),
                        NavItem("Tags", "admin_tags"),
                        NavItem("Maintenance", "admin_operations"),
                    ],
                ),
            ],
        ),
        "account": NavItem(
            "Account",
            children=[
                NavItem("Account", route_name="account", partial="nav_link_account"),
                NavItem(
                    "Log out",
                    route_name="logout",
                    partial="nav_link_logout",
                    view_condition=lambda r: r.identity is not None,
                ),
                NavItem(
                    "Log in",
                    route_name="login",
                    view_condition=lambda r: r.identity is None,
                ),
            ],
        ),
    }

    bound_roots: dict[str, BoundNavItem]

    def __init__(self, request: Request, options: dict):
        self.bound_roots = {}
        self.request = request
        for name, value in self.roots.items():
            self.bound_roots[name] = value.bind(request)

        self.unfocused = NavItem("", "").bind(request)

    def __getattr__(self, name):
        return self.bound_roots[name]

    @property
    def focused(self) -> BoundNavItem:
        items = list(self.bound_roots.values())
        while items:
            item = items.pop()
            if item.focused:
                return item
            items.extend(item.children)
        return self.unfocused  # XXX

    def subnav(self, level=2):
        # Find the relevant navigation X levels down from the
        # main navigation. Roots are level 0, main navigation is level 1,
        # first subnav level is level 2
        current_level = 0
        scope = self.bound_roots.values()
        while current_level < level:
            for candidate in scope:
                if candidate.active:
                    scope = list(candidate)
                    current_level += 1
                    break
            else:
                return []
        return scope


class PartialRenderer:
    def __init__(self, name, request):
        self.name = name
        self.request = request

    def __call__(self, **kw) -> Markup:
        return Markup(
            render(f"menage2:templates/partials/{self.name}.pt", kw, self.request)
        )


class Partials:
    def __init__(self, request):
        self.request = request
        # Also make accessible on request
        self.request.partials = self

    def __getattr__(self, name: str, /) -> Callable[..., Markup]:
        return PartialRenderer(name, self.request)

    __getitem__ = __getattr__


@subscriber(BeforeRender)
def add_partials(event):
    event["partials"] = Partials(event["request"])
