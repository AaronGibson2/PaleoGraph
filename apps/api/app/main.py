from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.db import create_db_engine
from app.discovery.routes import router as discovery_router
from app.errors import register_errors
from app.explore.routes import router as explore_router
from app.health import router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_db_engine(settings)
        application.state.db_engine = engine
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="PaleoGraph API", version="0.2.0", lifespan=lifespan)
    register_errors(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(router, prefix="/api/v1")
    application.include_router(explore_router, prefix="/api/v1")
    application.include_router(discovery_router, prefix="/api/v1")
    return application


app = create_app()
