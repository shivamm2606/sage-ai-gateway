import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# needed so create_all knows about every table on startup
from app import models  # noqa: F401
from app.api.routes import auth, chat, conversations, usage
from app.api.routes import models as models_routes
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
logger.info("starting %s in %s mode", settings.app_name, settings.environment)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database connected")
    yield
    await engine.dispose()


app = FastAPI(title="S.A.G.E", debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(models_routes.router)
app.include_router(usage.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
    }
