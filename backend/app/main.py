import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import AuthMiddleware
from app.bootstrap import init_database
from app.config import settings
from app.routes import router
from app.scheduler import start_background

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("datavines")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    if settings.auto_bootstrap_demo:
        try:
            from app.demo import bootstrap_demo

            logger.info("bootstrap demo: %s", bootstrap_demo())
        except Exception:
            logger.exception("demo bootstrap failed")
    start_background()
    yield


app = FastAPI(title="DataVines", version="1.0.0", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)


@app.get("/")
def root():
    return {"name": "DataVines", "api": settings.api_prefix, "docs": "/docs"}
