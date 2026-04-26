from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, Text
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

    passkeys = relationship("Passkey", back_populates="user", cascade="all, delete-orphan")


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
