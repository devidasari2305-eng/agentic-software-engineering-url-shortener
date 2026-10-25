from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import app.models  # noqa: F401  (register ORM models)
from app.api import urls, workflows
from app.core.database import Base, engine
from orchestrator.errors import (
    ApprovalError,
    InvalidRequest,
    InvalidTransition,
    WorkflowNotFound,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Agentic Software Engineering System - URL Shortener",
    version="3.0.0",
    description="A URL shortener plus a governed, stateful agentic SDLC orchestrator.",
    lifespan=lifespan,
)


def _error(status_code: int):
    async def handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


app.add_exception_handler(WorkflowNotFound, _error(404))
app.add_exception_handler(InvalidTransition, _error(409))
app.add_exception_handler(ApprovalError, _error(422))
app.add_exception_handler(InvalidRequest, _error(422))


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


app.include_router(urls.router)
app.include_router(workflows.router)
app.include_router(urls.redirect_router)  # catch-all `/{code}` must be registered last
