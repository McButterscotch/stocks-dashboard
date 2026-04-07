import os
import psycopg2
import sys

# ---------------------------------------------------------------------------
# Connection settings — match these to your docker-compose.yml environment
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),  # localhost because we're running outside Docker
    "port":     os.environ.get("DB_PORT", "5433"),
    "dbname":   os.environ.get("DB_NAME", "stocks"),
    "user":     os.environ.get("DB_USER", "stocks"),
    "password": os.environ.get("DB_PASSWORD", "stocks"),
}


def run_test(conn, label: str, query: str) -> None:
    """Run a single query and print the results in a readable way."""
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            col_names = [desc[0] for desc in cur.description]

            # Print column headers
            print("  " + "  |  ".join(col_names))
            print("  " + "-" * (len("  |  ".join(col_names)) + 2))

            if not rows:
                print("  (no rows returned)")
            else:
                for row in rows:
                    print("  " + "  |  ".join(str(v) for v in row))

    except Exception as e:
        print(f"  ERROR: {e}")


def main():
    print("\nConnecting to TimescaleDB...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("  ✓ Connection successful")
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        print("\n  Is the database running? Try: docker compose up -d timescaledb")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Test 1 — check TimescaleDB extension is active
    # -----------------------------------------------------------------------
    run_test(conn,
        "TimescaleDB extension",
        "SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';"
    )

    # -----------------------------------------------------------------------
    # Test 2 — list all tables
    # -----------------------------------------------------------------------
    run_test(conn,
        "Tables in database",
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
        """
    )

    # -----------------------------------------------------------------------
    # Test 3 — check hypertables (TimescaleDB-specific)
    # -----------------------------------------------------------------------
    run_test(conn,
        "Hypertables",
        "SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;"
    )

    # -----------------------------------------------------------------------
    # Test 4 — row counts per table
    # -----------------------------------------------------------------------
    run_test(conn,
        "Row counts",
        """
        SELECT 'companies'    AS table_name, COUNT(*) AS rows FROM companies
        UNION ALL
        SELECT 'stock_prices',               COUNT(*)         FROM stock_prices
        UNION ALL
        SELECT 'stock_metrics',              COUNT(*)         FROM stock_metrics;
        """
    )

    # -----------------------------------------------------------------------
    # Test 5 — sample of companies table
    # -----------------------------------------------------------------------
    run_test(conn,
        "Companies (first 5)",
        "SELECT ticker, name, sector FROM companies ORDER BY ticker LIMIT 5;"
    )

    # -----------------------------------------------------------------------
    # Test 6 — most recent prices per ticker
    # -----------------------------------------------------------------------
    run_test(conn,
        "Most recent price per ticker",
        """
        SELECT DISTINCT ON (ticker)
            ticker,
            time::date   AS date,
            close,
            volume
        FROM stock_prices
        ORDER BY ticker, time DESC;
        """
    )

    # -----------------------------------------------------------------------
    # Test 7 — most recent metrics for AAPL
    # -----------------------------------------------------------------------
    run_test(conn,
        "Latest metrics for AAPL",
        """
        SELECT
            time::date          AS date,
            ROUND(close::numeric,       2)  AS close,
            ROUND(sma_20::numeric,      2)  AS sma_20,
            ROUND(rsi_14::numeric,      1)  AS rsi_14,
            ROUND((daily_return * 100)::numeric, 2) AS daily_return_pct,
            ROUND((volatility_30d * 100)::numeric, 1) AS volatility_pct
        FROM stock_metrics
        JOIN stock_prices USING (time, ticker)
        WHERE ticker = 'AAPL'
        ORDER BY time DESC
        LIMIT 5;
        """
    )

    # -----------------------------------------------------------------------
    # Test 8 — date range of stored data
    # -----------------------------------------------------------------------
    run_test(conn,
        "Date range of stored data",
        """
        SELECT
            ticker,
            MIN(time)::date AS earliest,
            MAX(time)::date AS latest,
            COUNT(*)        AS trading_days
        FROM stock_prices
        GROUP BY ticker
        ORDER BY ticker;
        """
    )

    conn.close()
    print(f"\n{'─' * 60}")
    print("  All tests complete.")
    print(f"{'─' * 60}\n")


if __name__ == "__main__":
    main()
