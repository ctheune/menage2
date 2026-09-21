"""A principal is anything a task can be addressed to.

Both users and teams are named in the same breath -- `@matti`, `@eltern` --
and `principals.py` has always said the shared namespace was "enforced at
the application layer", which meant two admin views remembering to check.
Here the name lives in one table with one unique index, so a team cannot
take a user's name however the row was written.

Each user and each team owns exactly one row, kept in step by validators on
the name columns rather than by the views that write them: a User made in a
test or a script needs a principal just as much as one made through the
admin, and a rule that fires wherever the attribute is set cannot be
forgotten by a path that is added later.
"""

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .meta import Base


class Principal(Base):
    __tablename__ = "principals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    #: Derivable from which id is set, and kept anyway: it is what the
    #: pickers group by and what the assignee join will read.
    kind: Mapped[str] = mapped_column(Text, nullable=False)

    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), unique=True
    )

    user = relationship("User", back_populates="principal")
    team = relationship("Team", back_populates="principal")

    __table_args__ = (
        CheckConstraint(
            "(kind = 'user' AND user_id IS NOT NULL AND team_id IS NULL)"
            " OR (kind = 'team' AND team_id IS NOT NULL AND user_id IS NULL)",
            name="owner",
        ),
    )

    def __repr__(self) -> str:
        return f"<Principal {self.kind} {self.name!r}>"
