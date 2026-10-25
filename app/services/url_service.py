import secrets
import string
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.url import ClickEvent, ShortURL
from app.schemas.url import URLCreate

ALPHABET = string.ascii_letters + string.digits
MAX_CODE_ATTEMPTS = 10


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _allocate_code(db: Session, length: int = 7) -> str:
    for _ in range(MAX_CODE_ATTEMPTS):
        candidate = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if not db.scalar(select(ShortURL.id).where(ShortURL.code == candidate)):
            return candidate
    raise HTTPException(503, "Could not allocate a unique short code")


def create_url(db: Session, payload: URLCreate) -> ShortURL:
    expires_at = _aware(payload.expires_at)
    if expires_at is not None and expires_at <= _now():
        raise HTTPException(422, "expires_at must be in the future")

    target_host = urlparse(str(payload.target_url)).hostname
    if target_host and target_host == urlparse(settings.base_url).hostname:
        raise HTTPException(422, "Target URL must not point back to this service")

    code = payload.custom_code or _allocate_code(db)
    if db.scalar(select(ShortURL.id).where(ShortURL.code == code)):
        raise HTTPException(409, "Short code already exists")

    item = ShortURL(code=code, target_url=str(payload.target_url), expires_at=expires_at)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_url(db: Session, code: str) -> ShortURL:
    item = db.scalar(select(ShortURL).where(ShortURL.code == code))
    if item is None:
        raise HTTPException(404, "Short URL not found")
    return item


def ensure_resolvable(item: ShortURL) -> None:
    if not item.active:
        raise HTTPException(410, "Short URL is disabled")
    expires_at = _aware(item.expires_at)
    if expires_at is not None and expires_at <= _now():
        raise HTTPException(410, "Short URL has expired")


def record_click(db: Session, item: ShortURL, referrer: str | None, user_agent: str | None) -> None:
    # Atomic increment: avoids lost updates when concurrent redirects hit the same code.
    db.execute(update(ShortURL).where(ShortURL.id == item.id).values(clicks=ShortURL.clicks + 1))
    db.add(
        ClickEvent(
            short_url_id=item.id,
            referrer=referrer[:512] if referrer else None,
            user_agent=user_agent[:512] if user_agent else None,
        )
    )
    db.commit()


def to_response(item: ShortURL) -> dict:
    return {
        "code": item.code,
        "target_url": item.target_url,
        "short_url": f"{settings.base_url.rstrip('/')}/{item.code}",
        "created_at": item.created_at,
        "expires_at": item.expires_at,
        "active": item.active,
        "clicks": item.clicks,
    }
