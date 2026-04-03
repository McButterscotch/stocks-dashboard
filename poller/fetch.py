import time
import logging
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "NVDA", "TSLA", "JPM",  "BAC",  "V",
    "JNJ",  "PFE",  "XOM",  "CVX",  "WMT",
    "HD",   "DIS",  "NFLX", "INTC", "AMD",
]


def fetch_history(ticker: str, start: str, end: str = None) -> pd.DataFrame:
    """
    Fetch daily OHLCV data for a single ticker between start and end dates.

    start / end: strings in "YYYY-MM-DD" format.
    If end is None, yfinance defaults to today.

    Returns a clean DataFrame with columns:
        time, ticker, open, high, low, close, volume, adj_close
    Returns an empty DataFrame on failure.
    """
    try:
        raw = yf.download(
            ticker,
            start=start,
            end=end,
            interval="1d",
            auto_adjust=False,   # keep raw OHLC and Adj Close separate
            progress=False,      # suppress the tqdm progress bar
        )

        if raw.empty:
            logger.warning(f"No data returned for {ticker}.")
            return pd.DataFrame()

        # yfinance returns a DatetimeIndex; convert to a column
        raw = raw.reset_index()

        # yfinance column names have inconsistent casing; normalise them
        raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower()
                       for c in raw.columns]

        df = pd.DataFrame({
            "time":      pd.to_datetime(raw["date"]).dt.tz_localize("UTC"),
            "ticker":    ticker,
            "open":      raw["open"],
            "high":      raw["high"],
            "low":       raw["low"],
            "close":     raw["close"],
            "volume":    raw["volume"].astype("Int64"),
            "adj_close": raw["adj close"],
        })

        return df

    except Exception as e:
        logger.error(f"Failed to fetch history for {ticker}: {e}")
        return pd.DataFrame()


def fetch_all_history(start: str) -> pd.DataFrame:
    """
    Fetch history for all 20 tickers sequentially.
    Sleeps 1 second between each request to avoid rate limiting.
    Returns a combined DataFrame.
    """
    frames = []

    for ticker in TICKERS:
        logger.info(f"Fetching history for {ticker}...")
        df = fetch_history(ticker, start=start)
        if not df.empty:
            frames.append(df)
        time.sleep(1)   # be polite to Yahoo's servers

    if not frames:
        logger.error("fetch_all_history returned no data at all.")
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def fetch_latest(ticker: str) -> pd.DataFrame:
    """
    Fetch the most recent trading day's data for a single ticker.
    Used by the live poller (not the backfill).

    yfinance's "1d" period with "1m" interval gives intraday ticks,
    but for a daily pipeline "5d" period + "1d" interval is reliable
    and gives us the last few days as a safety buffer.
    """
    return fetch_history(
        ticker,
        start=pd.Timestamp.now(tz="UTC").floor("D").strftime("%Y-%m-%d"),
    )
