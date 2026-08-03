from contextlib import asynccontextmanager

import xgboost as xgb
from fastapi import FastAPI

from app.api.predictions import router as predictions_router
from app.api.tickers import router as tickers_router
from app.db.connection import init_db
from app.ml.training import MODEL_PATH


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.model = xgb.Booster()
    app.state.model.load_model(MODEL_PATH)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(tickers_router)
app.include_router(predictions_router)
