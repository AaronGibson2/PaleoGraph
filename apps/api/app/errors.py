import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, str]] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorBody


def register_errors(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        body = ErrorBody(
            code="INVALID_REQUEST",
            message="Check the requested bounds and parameters.",
            details=[
                {"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()
            ],
        )
        return JSONResponse(status_code=422, content=ErrorResponse(error=body).model_dump())

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        body = ErrorBody(
            code="NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR", message=str(exc.detail)
        )
        return JSONResponse(
            status_code=exc.status_code, content=ErrorResponse(error=body).model_dump()
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # Do not expose SQL, connection URLs, source payloads, or credentials.
        logger.error("Database request failed: %s", type(exc).__name__)
        body = ErrorBody(
            code="DATABASE_UNAVAILABLE", message="Occurrence data is temporarily unavailable."
        )
        return JSONResponse(status_code=503, content=ErrorResponse(error=body).model_dump())
