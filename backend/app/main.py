from contextlib import asynccontextmanager
from pathlib import Path

import xgboost as xgb
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load backend/.env before anything reads environment variables.
# This is a no-op if the file doesn't exist (safe for CI/production
# where env vars are injected directly).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.api.debate import router as debate_router
from app.api.insight import router as insight_router
from app.api.predictions import router as predictions_router
from app.api.tickers import router as tickers_router
from app.db.connection import init_db
from app.ml.training import MODEL_PATH

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
    app.state.model = xgb.Booster()
    app.state.model.load_model(MODEL_PATH)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tickers_router)
app.include_router(predictions_router)
app.include_router(insight_router)
app.include_router(debate_router)
