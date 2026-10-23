from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import Error, InterfaceError, OperationalError
from psycopg_pool import PoolTimeout

from app.config import Settings
from app.customers import router
from app.matching import router as matching_router
from app.db import create_pool, get_connection


def create_app(settings: Settings | None = None, pool=None) -> FastAPI:
    settings = settings or Settings()
    pool = pool if pool is not None else create_pool(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(app):
        pool.open(wait=False)
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(title="Zdieľňa API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.pool = pool
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["GET"], allow_headers=["Authorization"],
    )

    async def unavailable(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Databáza je momentálne nedostupná."})

    async def database_error(request, exc):
        return JSONResponse(status_code=500, content={"detail": "Databázový dotaz zlyhal. Overte schému a oprávnenia API."})

    app.add_exception_handler(Error, database_error)
    for exception in (OperationalError, InterfaceError, PoolTimeout):
        app.add_exception_handler(exception, unavailable)

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    @app.get("/ready", tags=["health"])
    def ready(conn=Depends(get_connection)):
        conn.execute("SELECT 1")
        return {"status": "ready"}

    app.include_router(router)
    app.include_router(matching_router)
    return app
