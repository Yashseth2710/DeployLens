from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PrimaryKeyMixin:
    """Postgres 18 generates uuidv7 natively. The values are time-ordered, so inserts
    land at the end of the index instead of scattering across it the way uuid4 does."""

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
