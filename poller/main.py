import logging
import time
from datetime import datetime, timezone

import pandas as pd
from apscheduler.schedulers.blocking import BlockingScheduler

from db import write_prices, write_metrics, get_latest_timestamp
from fetch import TICKERS, fetch_history, fetch_latest
from metrics import calculate_all_metrics, calculate_metrics

# ---------------------------------------------------------------------------
# Logging
# All modules use Python's standard logging. Configuring it once here
# means every logger.info() / logger.error() across all files flows
# through this format automatically.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

def backfill():
    """
    On first run, fetch 2 years of history for each ticker.
    On subsequent runs, only fetch data we're missing (incremental).

    This uses get_latest_timestamp() to find the last stored date per
    ticker. If we already have data up to yesterday, we skip that ticker.
    """
    two_years_ago = (
        pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=2)
    ).strftime("%Y-%m-%d")

    for ticker in TICKERS:
        latest = get_latest_timestamp(ticker)

        if latest is None:
            # No data at all — full 2-year fetch
            start = two_years_ago
            logger.info(f"[Backfill] {ticker}: no data found, fetching from {start}.")
        else:
            # We have some data — only fetch what's missing
            start = (latest + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            today = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")

            if start >= today:
                logger.info(f"[Backfill] {ticker}: already up to date, skipping.")
                continue

            logger.info(f"[Backfill] {ticker}: fetching from {start} onwards.")

        prices_df = fetch_history(ticker, start=start)

        if prices_df.empty:
            continue

        write_prices(prices_df)

        # Calculate metrics for the full history of this ticker
        # so rolling windows (e.g. SMA50) have enough lookback data.
        # We re-fetch all stored data for the ticker via a local concat.
        metrics_df = calculate_metrics(prices_df)
        write_metrics(metrics_df)

        time.sleep(1)  # rate limiting

    logger.info("Backfill complete.")


# ---------------------------------------------------------------------------
# Live polling job
# ---------------------------------------------------------------------------

def poll_live():
    """
    Fetches today's price for each ticker and updates the database.
    Scheduled to run every 5 minutes during market hours.

    Note: yfinance does not provide true real-time data. There is a
    15-minute delay. For a learning project this is fine. For production
    you would use a paid data provider (e.g. Alpaca, Polygon.io).
    """
    logger.info("Running live poll...")

    for ticker in TICKERS:
        df = fetch_latest(ticker)

        if df.empty:
            continue

        write_prices(df)
        metrics = calculate_metrics(df)
        write_metrics(metrics)

        time.sleep(0.5)

    logger.info("Live poll complete.")


def is_market_hours() -> bool:
    """
    Returns True if the current UTC time falls within NYSE trading hours:
    Monday–Friday, 14:30–21:00 UTC (= 9:30–16:00 US Eastern, ignoring DST).

    This is a simplified check. A production system would use a trading
    calendar library (e.g. `exchange_calendars`) to handle holidays.
    """
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:      # Saturday=5, Sunday=6
        return False
    return 14 <= now.hour < 21  # rough UTC window for NYSE


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Poller starting up. Running backfill...")
    backfill()

    scheduler = BlockingScheduler(timezone="UTC")

    # Run poll_live every 5 minutes
    # The job itself checks is_market_hours() so outside hours it exits fast
    scheduler.add_job(
        func=lambda: poll_live() if is_market_hours() else None,
        trigger="interval",
        minutes=5,
        id="live_poll",
    )

    logger.info("Scheduler started. Polling every 5 minutes.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Poller shut down cleanly.")
