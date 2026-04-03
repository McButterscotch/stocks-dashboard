import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# SQLAlchemy's create_engine() does NOT open a connection immediately.
# It creates a connection pool that hands out connections on demand.
# pool_pre_ping=True means: before using a connection from the pool,
# send a cheap "SELECT 1" to check it's still alive. This prevents
# errors after the database restarts or the connection idles out.
# ---------------------------------------------------------------------------

DB_URL = (
    f"postgresql+psycopg2://"
    f"{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
    f"@{os.environ['DB_HOST']}:5432/{os.environ['DB_NAME']}"
)

engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


def write_prices(df: pd.DataFrame) -> None:
    """
    Write a DataFrame of OHLCV rows to stock_prices.

    The DataFrame must have columns:
        time, ticker, open, high, low, close, volume, adj_close

    ON CONFLICT DO NOTHING means: if a row for (ticker, time) already
    exists, skip it silently. This makes the poller idempotent — you can
    run it twice without duplicating data, which is important during
    backfill or after a crash.
    """
    if df.empty:
        logger.warning("write_prices called with empty DataFrame, skipping.")
        return

    rows = df.to_dict(orient="records")

    sql = text("""
        INSERT INTO stock_prices
            (time, ticker, open, high, low, close, volume, adj_close)
        VALUES
            (:time, :ticker, :open, :high, :low, :close, :volume, :adj_close)
        ON CONFLICT (ticker, time) DO NOTHING
    """)

    with engine.begin() as conn:
        conn.execute(sql, rows)

    logger.info(f"Wrote {len(rows)} price rows to stock_prices.")


def write_metrics(df: pd.DataFrame) -> None:
    """
    Write a DataFrame of calculated metrics to stock_metrics.
    Same idempotency approach via ON CONFLICT DO NOTHING.
    """
    if df.empty:
        logger.warning("write_metrics called with empty DataFrame, skipping.")
        return

    rows = df.to_dict(orient="records")

    sql = text("""
        INSERT INTO stock_metrics (
            time, ticker, daily_return, sma_20, sma_50,
            ema_12, ema_26, macd, rsi_14, volatility_30d,
            bb_upper, bb_lower, cumulative_return, drawdown
        ) VALUES (
            :time, :ticker, :daily_return, :sma_20, :sma_50,
            :ema_12, :ema_26, :macd, :rsi_14, :volatility_30d,
            :bb_upper, :bb_lower, :cumulative_return, :drawdown
        )
        ON CONFLICT (ticker, time) DO NOTHING
    """)

    with engine.begin() as conn:
        conn.execute(sql, rows)

    logger.info(f"Wrote {len(rows)} metric rows to stock_metrics.")


def get_latest_timestamp(ticker: str) -> pd.Timestamp | None:
    """
    Returns the most recent 'time' stored for a given ticker,
    or None if no data exists yet. Used by the backfill logic
    to avoid re-fetching data we already have.
    """
    sql = text("""
        SELECT MAX(time) FROM stock_prices WHERE ticker = :ticker
    """)

    with engine.connect() as conn:
        result = conn.execute(sql, {"ticker": ticker}).scalar()

    return pd.Timestamp(result) if result else None
