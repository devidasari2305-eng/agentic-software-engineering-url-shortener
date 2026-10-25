from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class ShortURL(Base):
    __tablename__ = "short_urls"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    target_url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    events: Mapped[list["ClickEvent"]] = relationship(cascade="all, delete-orphan")


class ClickEvent(Base):
    __tablename__ = "click_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    short_url_id: Mapped[int] = mapped_column(ForeignKey("short_urls.id"), index=True)
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    referrer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
