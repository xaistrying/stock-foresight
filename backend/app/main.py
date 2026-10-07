import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load backend/.env before anything reads environment variables.
# This is a no-op if the file doesn't exist (safe for CI/production
# where env vars are injected directly).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.api.debate import router as debate_router
from app.api.range import router as range_router
from app.api.tickers import router as tickers_router
from app.db.connection import init_db
from app.services.debate import runner
from app.services.debate.llm_client import close_llm_clients

class _MaskingFormatter(logging.Formatter):
    """Masks key-shaped text (`sk-...`, `key-...`) in the whole formatted record, traceback included.

    Provider and CLI error text is logged by the agents; an SDK error body can quote a (masked) key.
    """

    _KEY_SHAPED = re.compile(r"\b(?:sk|key)-[A-Za-z0-9_\-*.]{6,}")

    def format(self, record: logging.LogRecord) -> str:
        return self._KEY_SHAPED.sub("[masked]", super().format(record))


def configure_logging() -> None:
    """INFO and up from the app's own loggers go to stderr (`.run/backend.log` under `make up`).

    uvicorn configures only its own loggers. Without this the per-run debate line
    (`app.services.debate.runner`) and every other INFO line of `app.*` would be dropped, and only
    warnings would reach the log.
    """
    app_logger = logging.getLogger("app")
    if not any(isinstance(handler, logging.StreamHandler) for handler in app_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(_MaskingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)


configure_logging()

# Vite dev server origins only (frontend/README, `npm run dev` default).
# No production frontend origin exists yet — add it here once M5 ships to
# a real host rather than widening this to a wildcard.
DEV_FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    await runner.shutdown()  # runs outlive their requests: stop them before their clients close
    await close_llm_clients()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tickers_router)
app.include_router(debate_router)
app.include_router(range_router)
