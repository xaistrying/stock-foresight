"""GET /tickers/{ticker}/range: the calibrated 5-session band, its coverage and its status."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.services.range import TickerNotLoaded, compute_range

router = APIRouter()


@router.get("/tickers/{ticker}/range")
def get_range(ticker: str) -> dict:
    try:
        return asdict(compute_range(ticker))
    except TickerNotLoaded:
        raise HTTPException(status_code=404, detail="Ticker has not been loaded")
