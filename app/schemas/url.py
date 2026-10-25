from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class URLCreate(BaseModel):
    target_url: HttpUrl
    custom_code: str | None = Field(
        default=None, min_length=4, max_length=16, pattern=r"^[A-Za-z0-9_-]+$"
    )
    expires_at: datetime | None = None


class URLResponse(BaseModel):
    code: str
    target_url: str
    short_url: str
    created_at: datetime
    expires_at: datetime | None
    active: bool
    clicks: int


class AnalyticsResponse(BaseModel):
    code: str
    clicks: int
    created_at: datetime
    last_clicked_at: datetime | None
    active: bool
    expires_at: datetime | None
