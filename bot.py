
import requests
from datetime import datetime, timezone

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"

def get_btc_candles(limit=1000):
    response = requests.get(
        BINANCE_URL,
        params={
            "symbol": "BTCUSDT",
            "interval": "1m",
            "limit": limit,
        },
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()

    return [
        {
            "time": datetime.fromtimestamp(
                row[0] / 1000, tz=timezone.utc
            ).isoformat(),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "closed": row[6] < int(datetime.now(
                timezone.utc
            ).timestamp() * 1000),
        }
        for row in rows
    ]

def get_market_status():
    try:
        candles = get_btc_candles()
        return {
            "status": "ok",
            "mode": "PAPER ONLY",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "candles_received": len(candles),
            "latest_close": candles[-1]["close"],
            "latest_candle_time": candles[-1]["time"],
            "note": "Market data only; no trades are placed.",
        }
    except Exception as exc:
        return {
            "status": "error",
            "mode": "PAPER ONLY",
            "error": str(exc),
        }
