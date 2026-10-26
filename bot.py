
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"


def get_btc_candles(limit=3000):
    candles = []
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_time = None

    # Binance allows at most 1000 candles per request.
    while len(candles) < limit:
        params = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "limit": min(1000, limit - len(candles)),
        }
        if end_time is not None:
            params["endTime"] = end_time

        response = requests.get(
            BINANCE_URL, params=params, timeout=20
        )
        response.raise_for_status()
        rows = response.json()

        if not rows:
            break

        candles = rows + candles
        end_time = rows[0][0] - 1

        if len(rows) < 1000:
            break

    # Remove any duplicates and keep chronological order.
    unique_rows = {row[0]: row for row in candles}
    candles = [
        unique_rows[t] for t in sorted(unique_rows)
    ][-limit:]

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
            "closed": int(row[6]) < now_ms,
        }
        for row in candles
    ]


def calculate_stvpt(candles, multiplier, period=100, length=2000):
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

    last_trend = int(trend.iloc[-1])
    last_line = (
        up_trend.iloc[-1] if last_trend == 1
        else down_trend.iloc[-1]
    )

    return {
        "trend": last_trend,
        "color": "GREEN" if last_trend == 1 else "RED",
        "line": float(last_line) if pd.notna(last_line) else None,
        "multiplier": multiplier,
        "period": period,
        "ema_length": length,
    }


def get_market_status():
    try:
        candles = get_btc_candles(limit=3000)
        closed_candles = [
            candle for candle in candles if candle["closed"]
        ]

        if len(closed_candles) < 2200:
            return {
                "status": "waiting",
                "mode": "PAPER ONLY",
                "closed_candles_received": len(closed_candles),
                "message": (
                    "Waiting for at least 2200 closed candles "
                    "for EMA 2000 calculations."
                ),
            }

        main = calculate_stvpt(
            closed_candles, multiplier=5, period=100, length=2000
        )
        fast = calculate_stvpt(
            closed_candles, multiplier=0.5, period=100, length=2000
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
                "Diagnostic only; not yet verified against "
                "TradingView. No trades are placed."
            ),
        }

    except Exception as exc:
        return {
            "status": "error",
            "mode": "PAPER ONLY",
            "error": str(exc),
        }
