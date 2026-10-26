
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"

# Your TradingView STVPT settings
CANDLE_LIMIT = 3000
STVPT_LENGTH = 2000
SUPERTREND_PERIOD = 100
MAIN_MULTIPLIER = 5.0
FAST_MULTIPLIER = 0.5


def get_btc_candles(limit=CANDLE_LIMIT):
    """Fetch historical BTCUSDT one-minute candles from Binance."""
    rows_all = []
    end_time = None

    while len(rows_all) < limit:
        params = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "limit": min(1000, limit - len(rows_all)),
        }

        if end_time is not None:
            params["endTime"] = end_time

        response = requests.get(
            BINANCE_URL,
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        rows = response.json()

        if not rows:
            break

        rows_all = rows + rows_all
        end_time = rows[0][0] - 1

        if len(rows) < 1000:
            break

    unique_rows = {row[0]: row for row in rows_all}
    rows_all = [
        unique_rows[t] for t in sorted(unique_rows)
    ][-limit:]

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

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
        for row in rows_all
    ]


def pine_ema(series, length):
    """EMA with Pine-style SMA initialization."""
    result = pd.Series(np.nan, index=series.index, dtype=float)

    valid = series.first_valid_index()
    if valid is None:
        return result

    start = series.index.get_loc(valid)
    alpha = 2.0 / (length + 1.0)

    seed_end = start + length
    if seed_end > len(series):
        return result

    seed_values = series.iloc[start:seed_end]
    if seed_values.isna().any():
        return result

    result.iloc[seed_end - 1] = seed_values.mean()

    for i in range(seed_end, len(series)):
        value = series.iloc[i]
        previous = result.iloc[i - 1]

        if pd.isna(value) or pd.isna(previous):
            result.iloc[i] = np.nan
        else:
            result.iloc[i] = alpha * value + (1 - alpha) * previous

    return result


def pine_rma(series, length):
    """Wilder's RMA, used by TradingView ATR."""
    result = pd.Series(np.nan, index=series.index, dtype=float)

    valid = series.first_valid_index()
    if valid is None:
        return result

    start = series.index.get_loc(valid)
    seed_end = start + length

    if seed_end > len(series):
        return result

    seed_values = series.iloc[start:seed_end]
    if seed_values.isna().any():
        return result

    result.iloc[seed_end - 1] = seed_values.mean()

    for i in range(seed_end, len(series)):
        value = series.iloc[i]
        previous = result.iloc[i - 1]

        if pd.isna(value) or pd.isna(previous):
            result.iloc[i] = np.nan
        else:
            result.iloc[i] = (
                previous * (length - 1) + value
            ) / length

    return result


def calculate_stvpt(
    candles,
    multiplier,
    period=SUPERTREND_PERIOD,
    length=STVPT_LENGTH,
):
    """Calculate diagnostic STVPT values from closed candles."""
    df = pd.DataFrame(candles).reset_index(drop=True)

    high = df["high"]
    low = df["low"]
    close = df["close"]
    open_price = df["open"]
    volume = df["volume"]

    hilow = (high - low) * 100
    openclose = (close - open_price) * 100

    vol = volume.div(hilow.replace(0, np.nan))
    spreadvol = (openclose * vol).replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0)

    # Preserve the cumulative VPT-style calculation.
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

    vpt = pine_ema(out, length)

    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = pine_rma(true_range, period)

    up_lev = vpt - multiplier * atr
    dn_lev = vpt + multiplier * atr

    up_trend = pd.Series(np.nan, index=df.index, dtype=float)
    down_trend = pd.Series(np.nan, index=df.index, dtype=float)
    trend = pd.Series(0, index=df.index, dtype=int)

    for i in range(len(df)):
        if i == 0:
            up_trend.iloc[i] = up_lev.iloc[i]
            down_trend.iloc[i] = dn_lev.iloc[i]
            trend.iloc[i] = 1
            continue

        prev_up = up_trend.iloc[i - 1]
        prev_down = down_trend.iloc[i - 1]

        current_up = up_lev.iloc[i]
        current_down = dn_lev.iloc[i]

        if pd.isna(current_up) or pd.isna(current_down):
            up_trend.iloc[i] = current_up
            down_trend.iloc[i] = current_down
            trend.iloc[i] = trend.iloc[i - 1]
            continue

        up_trend.iloc[i] = (
            max(current_up, prev_up)
            if close.iloc[i - 1] > prev_up
            else current_up
        )

        down_trend.iloc[i] = (
            min(current_down, prev_down)
            if close.iloc[i - 1] < prev_down
            else current_down
        )

        if close.iloc[i] > prev_down:
            trend.iloc[i] = 1
        elif close.iloc[i] < prev_up:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i - 1]

    last_i = len(df) - 1
    previous_i = last_i - 1

    def line_at(i, direction):
        value = (
            up_trend.iloc[i]
            if direction == 1
            else down_trend.iloc[i]
        )
        return float(value) if pd.notna(value) else None

    current_trend = int(trend.iloc[last_i])
    previous_trend = int(trend.iloc[previous_i])

    # Pine plots st_line[1] but colors it with the current trend.
    return {
        "trend": current_trend,
        "color": "GREEN" if current_trend == 1 else "RED",
        "line": line_at(last_i, current_trend),
        "plotted_line": line_at(previous_i, previous_trend),
        "plotted_color": (
            "GREEN" if current_trend == 1 else "RED"
        ),
        "multiplier": multiplier,
        "period": period,
        "ema_length": length,
    }


def get_market_status():
    try:
        candles = get_btc_candles(CANDLE_LIMIT)

        closed_candles = [
            candle for candle in candles if candle["closed"]
        ]

        if len(closed_candles) < 2200:
            return {
                "status": "waiting",
                "mode": "PAPER ONLY",
                "closed_candles_received": len(closed_candles),
                "message": "Waiting for at least 2200 closed candles.",
            }

        main = calculate_stvpt(
            closed_candles,
            multiplier=MAIN_MULTIPLIER,
        )

        fast = calculate_stvpt(
            closed_candles,
            multiplier=FAST_MULTIPLIER,
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
                "Diagnostic only; exact TradingView parity is "
                "not confirmed. No trades are placed."
            ),
        }

    except Exception as exc:
        return {
            "status": "error",
            "mode": "PAPER ONLY",
            "error": str(exc),
        }
