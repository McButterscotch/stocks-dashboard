import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_metrics(prices_df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a DataFrame of raw prices for a SINGLE ticker (sorted by time),
    returns a DataFrame of calculated metrics with the same index.

    Input columns expected: time, ticker, close
    Output adds:
        daily_return, sma_20, sma_50, ema_12, ema_26, macd,
        rsi_14, volatility_30d, bb_upper, bb_lower,
        cumulative_return, drawdown
    """
    df = prices_df.sort_values("time").copy()

    close = df["close"]

    # ------------------------------------------------------------------
    # Daily return
    # (today - yesterday) / yesterday
    # pct_change() handles this cleanly; first row becomes NaN.
    # ------------------------------------------------------------------
    df["daily_return"] = close.pct_change()

    # ------------------------------------------------------------------
    # Simple Moving Averages
    # rolling(n).mean() requires n non-NaN values before producing output.
    # min_periods=1 would give a partial average early on — we leave it
    # at the default (min_periods = window) so early rows are NaN rather
    # than misleadingly smooth.
    # ------------------------------------------------------------------
    df["sma_20"] = close.rolling(window=20).mean()
    df["sma_50"] = close.rolling(window=50).mean()

    # ------------------------------------------------------------------
    # Exponential Moving Averages (used for MACD)
    # ewm() applies exponentially decaying weights — recent prices count
    # more. span=12 / span=26 are the standard MACD parameters.
    # adjust=False uses the recursive formula, which is more memory-
    # efficient for streaming data.
    # ------------------------------------------------------------------
    df["ema_12"] = close.ewm(span=12, adjust=False).mean()
    df["ema_26"] = close.ewm(span=26, adjust=False).mean()
    df["macd"]   = df["ema_12"] - df["ema_26"]

    # ------------------------------------------------------------------
    # RSI (Relative Strength Index, 14-day)
    # Measures momentum: ratio of average gains to average losses.
    # Above 70 = overbought (potential sell signal).
    # Below 30 = oversold (potential buy signal).
    # ------------------------------------------------------------------
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()

    # Avoid division by zero when loss is 0 (pure uptrend)
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # ------------------------------------------------------------------
    # Annualised 30-day rolling volatility
    # std of daily returns * sqrt(252) converts daily volatility to an
    # annualised figure. 252 = trading days in a year.
    # ------------------------------------------------------------------
    df["volatility_30d"] = (
        df["daily_return"].rolling(30).std() * np.sqrt(252)
    )

    # ------------------------------------------------------------------
    # Bollinger Bands (20-day, 2 standard deviations)
    # Upper / lower bands = SMA20 ± 2σ.
    # Price touching the upper band suggests overbought;
    # touching lower suggests oversold.
    # ------------------------------------------------------------------
    rolling_std  = close.rolling(20).std()
    df["bb_upper"] = df["sma_20"] + 2 * rolling_std
    df["bb_lower"] = df["sma_20"] - 2 * rolling_std

    # ------------------------------------------------------------------
    # Cumulative return
    # Total percentage gain from the first data point.
    # cumprod() chains the daily multipliers: (1+r1)*(1+r2)*...
    # ------------------------------------------------------------------
    df["cumulative_return"] = (1 + df["daily_return"]).cumprod() - 1

    # ------------------------------------------------------------------
    # Drawdown
    # How far the price has fallen from its running all-time high.
    # Useful for visualising risk and recovery periods.
    # expanding().max() gives the running maximum up to each point.
    # ------------------------------------------------------------------
    running_max    = close.expanding().max()
    df["drawdown"] = (close - running_max) / running_max

    # Keep only the columns the metrics table expects
    metric_cols = [
        "time", "ticker", "daily_return", "sma_20", "sma_50",
        "ema_12", "ema_26", "macd", "rsi_14", "volatility_30d",
        "bb_upper", "bb_lower", "cumulative_return", "drawdown",
    ]

    return df[metric_cols]


def calculate_all_metrics(prices_df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies calculate_metrics() to each ticker in a combined DataFrame.
    Splits by ticker, processes each, then recombines.
    """
    frames = []

    for ticker, group in prices_df.groupby("ticker"):
        try:
            metrics = calculate_metrics(group)
            frames.append(metrics)
        except Exception as e:
            logger.error(f"Metric calculation failed for {ticker}: {e}")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)
