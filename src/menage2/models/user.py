from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
)
from sqlalchemy.orm import relationship

from .meta import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(Text, nullable=False, unique=True)
    real_name = Column(Text, nullable=False)
    email = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text, nullable=True)
    is_admin = Column(Boolean, nullable=False, server_default="false")
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    password_reset_token = Column(Text, nullable=True, unique=True)
    password_reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    passkeys = relationship(
        "Passkey", back_populates="user", cascade="all, delete-orphan"
    )
    absences = relationship(
        "Absence",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Absence.starts_on",
    )


#: A Monday start and a Friday end are taken to include the weekend beside
#: them: somebody off all week is not back for the Saturday in the middle of
#: it, and was not there for the Sunday before.
_WEEKEND_BEFORE = 0  # Monday
_WEEKEND_AFTER = 4  # Friday


class Absence(Base):
    """A stretch of days somebody is away.

    Both days are inclusive — "away 12th to 14th" means away on the 14th,
    which is how people say it and how it reads back.
    """

    __tablename__ = "absences"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    starts_on = Column(Date, nullable=False)
    ends_on = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="absences")

    __table_args__ = (
        CheckConstraint("ends_on >= starts_on", name="ck_absences_dates"),
    )

    @property
    def covers_from(self):
        """The first day they are counted as away.

        A week off starting on a Monday takes the weekend before it with it:
        nobody books the Saturday to say they will not be working.
        """
        from datetime import timedelta

        if self.starts_on.weekday() == _WEEKEND_BEFORE:
            return self.starts_on - timedelta(days=2)
        return self.starts_on

    @property
    def covers_until(self):
        """The last day they are counted as away, weekend after included."""
        from datetime import timedelta

        if self.ends_on.weekday() == _WEEKEND_AFTER:
            return self.ends_on + timedelta(days=2)
        return self.ends_on

    def covers(self, day) -> bool:
        return self.covers_from <= day <= self.covers_until


class Passkey(Base):
    __tablename__ = "passkeys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    credential_id = Column(LargeBinary, nullable=False, unique=True)
    credential_public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(Integer, nullable=False, server_default="0")
    device_name = Column(Text, nullable=False, default="Passkey")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="passkeys")
