from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.tickers import router as tickers_router
from app.db.connection import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(tickers_router)
