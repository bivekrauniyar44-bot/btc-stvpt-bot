
import requests
import numpy as np
import pandas as pd
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
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    candles = []
    for row in rows:
        candles.append({
            "time": datetime.fromtimestamp(
                row[0] / 1000, tz=timezone.utc
            ).isoformat(),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "closed": int(row[6]) < now_ms,
        })

    return candles


def calculate_stvpt(candles, multiplier, period=100, length=10):
    df = pd.DataFrame(candles)

    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    hilow = (high - low) * 100
    openclose = (close - df["open"]) * 100

    vol = volume.div(hilow.replace(0, np.nan))
    spreadvol = (openclose * vol).replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0)

    v = spreadvol.cumsum()
    smooth = v.rolling(14, min_periods=14).mean()
    price_spread = (high - low).rolling(
        28, min_periods=28
    ).std(ddof=1)
    v_spread = (v - smooth).rolling(
        28, min_periods=28
    ).std(ddof=1)

    shadow = (v - smooth).div(
        v_spread.replace(0, np.nan)
    ) * price_spread
    shadow = shadow.replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0)

    out = pd.Series(
        np.where(shadow > 0, high + shadow, low + shadow),
        index=df.index,
    )
    vpt = out.ewm(
        span=length, adjust=False, min_periods=length
    ).mean()

    previous_close = close.shift(1)
    true_range = pd.concat([
        high - low,
        (high - previous_close).abs(),
        (low - previous_close).abs(),
    ], axis=1).max(axis=1)

    atr = true_range.ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean()

    up_lev = vpt - multiplier * atr
    dn_lev = vpt + multiplier * atr

    up_trend = pd.Series(np.nan, index=df.index)
    down_trend = pd.Series(np.nan, index=df.index)
    trend = pd.Series(0, index=df.index, dtype=int)

    for i in range(len(df)):
        if i == 0:
            up_trend.iloc[i] = up_lev.iloc[i]
            down_trend.iloc[i] = dn_lev.iloc[i]
            trend.iloc[i] = 1
            continue

        prev_up = up_trend.iloc[i - 1]
        prev_down = down_trend.iloc[i - 1]

        up_trend.iloc[i] = (
            max(up_lev.iloc[i], prev_up)
            if close.iloc[i - 1] > prev_up
            else up_lev.iloc[i]
        )

        down_trend.iloc[i] = (
            min(dn_lev.iloc[i], prev_down)
            if close.iloc[i - 1] < prev_down
            else dn_lev.iloc[i]
        )

        if close.iloc[i] > down_trend.iloc[i - 1]:
            trend.iloc[i] = 1
        elif close.iloc[i] < up_trend.iloc[i - 1]:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i - 1]

    return {
        "trend": int(trend.iloc[-1]),
        "color": "GREEN" if trend.iloc[-1] == 1 else "RED",
        "line": float(
            up_trend.iloc[-1]
            if trend.iloc[-1] == 1
            else down_trend.iloc[-1]
        ) if pd.notna(
            up_trend.iloc[-1]
            if trend.iloc[-1] == 1
            else down_trend.iloc[-1]
        ) else None,
    }


def get_market_status():
    try:
        candles = get_btc_candles()

        # Exclude the currently forming candle.
        closed_candles = [
            candle for candle in candles if candle["closed"]
        ]

        if len(closed_candles) < 200:
            return {
                "status": "waiting",
                "mode": "PAPER ONLY",
                "message": "Not enough closed candles yet.",
            }

        main = calculate_stvpt(
            closed_candles, multiplier=5, period=100, length=10
        )
        fast = calculate_stvpt(
            closed_candles, multiplier=0.5, period=100, length=10
        )

        return {
            "status": "ok",
            "mode": "PAPER ONLY",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "closed_candles_received": len(closed_candles),
            "latest_closed_candle_time": closed_candles[-1]["time"],
            "latest_closed_price": closed_candles[-1]["close"],
            "main_stvpt": main,
            "fast_stvpt": fast,
            "note": (
                "Diagnostic signals only. Not verified against "
                "TradingView; no trades are placed."
            ),
        }

    except Exception as exc:
        return {
            "status": "error",
            "mode": "PAPER ONLY",
            "error": str(exc),
        }
