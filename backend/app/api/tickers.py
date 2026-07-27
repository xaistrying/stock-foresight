from fastapi import APIRouter

from app.services.ticker_ingestion import load_ticker

router = APIRouter()


@router.post("/tickers/{ticker}/load")
def load_ticker_endpoint(ticker: str):
    return load_ticker(ticker)
