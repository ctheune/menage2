from sqlalchemy import Column, Text

from .meta import Base


class ConfigItem(Base):
    __tablename__ = "config_items"

    key = Column(Text, primary_key=True)
    value = Column(Text, nullable=True)
