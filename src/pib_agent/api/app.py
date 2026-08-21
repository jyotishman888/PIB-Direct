from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pib_agent.api.routers import admin, articles, auth, health, ministries, topics
from pib_agent.config import get_settings
from pib_agent.orchestration import start_scheduler, stop_scheduler

# Everything the API serves lives under /api so a single origin can serve both
# the API and the SPA. They genuinely collide otherwise — `/articles` is an
# endpoint *and* a frontend route. One origin is what keeps the session cookie
# first-party; splitting them across hosts would require SameSite=None
# third-party cookies, which browsers increasingly block.
API_PREFIX = "/api"


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


def _static_dir() -> Path | None:
    """The built frontend, if it was bundled into the image."""
    candidate = Path(__file__).resolve().parents[1] / "static"
    return candidate if (candidate / "index.html").exists() else None


def _mount_frontend(application: FastAPI) -> None:
    """Serve the built SPA alongside the API, when present.

    Absent in local development — the Vite dev server handles the frontend and
    proxies /api here — so this is a no-op unless a build was copied in.
    """
    static_dir = _static_dir()
    if static_dir is None:
        return

    application.mount(
        "/assets", StaticFiles(directory=static_dir / "assets"), name="assets"
    )

    index = static_dir / "index.html"

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        """Return index.html for any non-API path.

        Client-side routes like /articles/1 and /account have no server-side
        counterpart, so without this a hard refresh on one 404s. Registered
        after the API routers, so it only catches what they didn't.
        """
        requested = static_dir / full_path
        if full_path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(index)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="PIB Agent API",
        description="Ministry-wise dashboard API for enriched PIB releases.",
        version="0.1.0",
        lifespan=_lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
    )
    # Only needed when the frontend is served from a different origin, i.e.
    # the Vite dev server. In production both come off one origin.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        health.router,
        auth.router,
        ministries.router,
        topics.router,
        articles.router,
        admin.router,
    ):
        application.include_router(router, prefix=API_PREFIX)

    _mount_frontend(application)
    return application


app = create_app()
