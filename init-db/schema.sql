-- Enable the TimescaleDB extension (must come first)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- Company metadata
-- Static reference data. One row per ticker, never time-series.
-- Stored in a plain table (no hypertable needed).
-- ============================================================
CREATE TABLE IF NOT EXISTS companies (
    ticker      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sector      TEXT
);

-- Pre-populate with our 20 tickers
INSERT INTO companies (ticker, name, sector) VALUES
    ('AAPL',  'Apple Inc.',                   'Technology'),
    ('MSFT',  'Microsoft Corporation',         'Technology'),
    ('GOOGL', 'Alphabet Inc.',                 'Technology'),
    ('AMZN',  'Amazon.com Inc.',               'Consumer Cyclical'),
    ('META',  'Meta Platforms Inc.',            'Technology'),
    ('NVDA',  'NVIDIA Corporation',             'Technology'),
    ('TSLA',  'Tesla Inc.',                     'Consumer Cyclical'),
    ('JPM',   'JPMorgan Chase & Co.',           'Financial Services'),
    ('BAC',   'Bank of America Corp.',          'Financial Services'),
    ('V',     'Visa Inc.',                      'Financial Services'),
    ('JNJ',   'Johnson & Johnson',              'Healthcare'),
    ('PFE',   'Pfizer Inc.',                    'Healthcare'),
    ('XOM',   'Exxon Mobil Corporation',        'Energy'),
    ('CVX',   'Chevron Corporation',            'Energy'),
    ('WMT',   'Walmart Inc.',                   'Consumer Defensive'),
    ('HD',    'The Home Depot Inc.',            'Consumer Cyclical'),
    ('DIS',   'The Walt Disney Company',        'Communication Services'),
    ('NFLX',  'Netflix Inc.',                   'Communication Services'),
    ('INTC',  'Intel Corporation',              'Technology'),
    ('AMD',   'Advanced Micro Devices Inc.',    'Technology');

-- ============================================================
-- Raw price data
-- One row per ticker per trading day.
-- This is the core time-series table.
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_prices (
    time        TIMESTAMPTZ         NOT NULL,
    ticker      TEXT                NOT NULL REFERENCES companies(ticker),
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION    NOT NULL,
    volume      BIGINT,
    adj_close   DOUBLE PRECISION
);

-- Convert to a hypertable, partitioned by time.
-- TimescaleDB will automatically split data into chunks (default: 7 days each).
-- This makes time-range queries dramatically faster on large datasets.
SELECT create_hypertable('stock_prices', 'time');

-- Composite index: when Grafana queries "give me AAPL for the last 30 days"
-- the database can jump straight to the AAPL partition in the right time range.
CREATE INDEX ON stock_prices (ticker, time DESC);

-- Prevent duplicate rows if the poller runs twice for the same day
CREATE UNIQUE INDEX ON stock_prices (ticker, time);

-- ============================================================
-- Calculated metrics
-- Derived from stock_prices by the Python poller.
-- Also a hypertable because it has the same time-series shape.
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_metrics (
    time            TIMESTAMPTZ     NOT NULL,
    ticker          TEXT            NOT NULL REFERENCES companies(ticker),
    daily_return    DOUBLE PRECISION,
    sma_20          DOUBLE PRECISION,
    sma_50          DOUBLE PRECISION,
    ema_12          DOUBLE PRECISION,
    ema_26          DOUBLE PRECISION,
    macd            DOUBLE PRECISION,
    rsi_14          DOUBLE PRECISION,
    volatility_30d  DOUBLE PRECISION,
    bb_upper        DOUBLE PRECISION,
    bb_lower        DOUBLE PRECISION,
    cumulative_return DOUBLE PRECISION,
    drawdown        DOUBLE PRECISION
);

SELECT create_hypertable('stock_metrics', 'time');

CREATE INDEX ON stock_metrics (ticker, time DESC);
CREATE UNIQUE INDEX ON stock_metrics (ticker, time);
