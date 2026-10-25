from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.url import ClickEvent
from app.schemas.url import AnalyticsResponse, URLCreate, URLResponse
from app.services import url_service

router = APIRouter(prefix="/api/urls", tags=["urls"])
redirect_router = APIRouter(tags=["redirect"])


@router.post("", response_model=URLResponse, status_code=status.HTTP_201_CREATED)
def create(payload: URLCreate, db: Session = Depends(get_db)):
    return url_service.to_response(url_service.create_url(db, payload))


@router.get("/{code}", response_model=URLResponse)
def details(code: str, db: Session = Depends(get_db)):
    return url_service.to_response(url_service.get_url(db, code))


@router.get("/{code}/analytics", response_model=AnalyticsResponse)
def analytics(code: str, db: Session = Depends(get_db)):
    item = url_service.get_url(db, code)
    last_clicked_at = db.scalar(
        select(ClickEvent.clicked_at)
        .where(ClickEvent.short_url_id == item.id)
        .order_by(ClickEvent.clicked_at.desc())
        .limit(1)
    )
    return {
        "code": item.code,
        "clicks": item.clicks,
        "created_at": item.created_at,
        "last_clicked_at": last_clicked_at,
        "active": item.active,
        "expires_at": item.expires_at,
    }


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
def disable(code: str, db: Session = Depends(get_db)):
    item = url_service.get_url(db, code)
    item.active = False
    db.commit()


@redirect_router.get("/{code}")
def redirect(code: str, request: Request, db: Session = Depends(get_db)):
    item = url_service.get_url(db, code)
    url_service.ensure_resolvable(item)
    url_service.record_click(
        db, item, request.headers.get("referer"), request.headers.get("user-agent")
    )
    return RedirectResponse(item.target_url, status_code=307)
