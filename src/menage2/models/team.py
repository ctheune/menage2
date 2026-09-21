import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from .meta import Base


def _principal(kind: str, name: str):
    """Deferred: principal.py is imported through models/__init__ too."""
    from .principal import Principal

    return Principal(kind=kind, name=name)


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    principal = relationship(
        "Principal",
        back_populates="team",
        uselist=False,
        cascade="all, delete-orphan",
    )

    #: See User.username -- one namespace, held on the principal.
    name = association_proxy(
        "principal",
        "name",
        creator=lambda name: _principal("team", name),
    )

    members = relationship(
        "TeamMember", cascade="all, delete-orphan", back_populates="team"
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(Text, nullable=False)

    user = relationship("User")
    team = relationship("Team", back_populates="members")

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        # Bare name: the ``ck_`` convention prefixes it with the table.
        CheckConstraint("role IN ('assignee', 'supervisor')", name="role"),
    )
