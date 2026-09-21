"""Who an item is for, as references rather than as text.

`assignees` was an array of strings, so `@nobdoy` stored happily and
addressed no one -- and production carried 211 values that were two names
jammed into one. An assignment is now a row pointing at a principal, and
the database will not hold one that names nobody.

``Item.assignees`` is still a ``set[str]``, because every visibility rule
in `principals.py` is set intersection over names and none of it needed to
change. See models/nameset.py.
"""

from sqlalchemy import Column, ForeignKey, Index, Integer, Table, select
from sqlalchemy.orm import Session

from .meta import Base
from .principal import Principal

#: Who an item is for. Indexed by principal too: "everything assigned to
#: this team" is the direction the filters ask in.
item_assignees = Table(
    "item_assignees",
    Base.metadata,
    Column(
        "item_id",
        Integer,
        ForeignKey("items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "principal_id",
        Integer,
        ForeignKey("principals.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_item_assignees_principal_id", "principal_id"),
)


class UnknownPrincipal(LookupError):
    """A name that addresses nobody.

    Raised where the assignment would be written. Views check first, so
    that the person who typed it gets told rather than the request failing
    -- this is the backstop for a path that forgets to.
    """

    def __init__(self, name: str):
        super().__init__(f"no user or team is called {name!r}")
        self.name = name


def principal_named(session: Session, name: str) -> Principal:
    """The principal called `name`. It has to be one; nothing is invented."""
    cache = session.info.setdefault("principals_seen", {})
    principal = cache.get(name)
    if principal is not None:
        return principal
    with session.no_autoflush:
        principal = session.execute(
            select(Principal).where(Principal.name == name)
        ).scalar_one_or_none()
    if principal is None:
        raise UnknownPrincipal(name)
    cache[name] = principal
    return principal
