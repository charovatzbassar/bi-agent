# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A small Python ETL project that loads the "Superstore" retail dataset into a
PostgreSQL star-schema data warehouse, which is then visualized in Apache
Superset. There is no application server or frontend — this repo is just the
ETL scripts, the schema DDL, and source data.

## Commands

```bash
pip install -r requirements.txt   # deps: pandas, psycopg2-binary, python-dotenv
python etl_process.py             # main ETL: loads Superstore.csv into the star schema
python etl_process2.py            # secondary ETL: loads product_search.txt into dim_product_recommendations
```

Database connection is configured via a git-ignored `.env` file with
`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DATABASE`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`. Apply `schema.sql` to the target Postgres database before
running either ETL script — the scripts do not create tables themselves.

There is no test suite, linter, or build step in this repo.

## Architecture

- `schema.sql` — star schema DDL: `fact_sales` plus dimensions `dim_date`,
  `dim_customer`, `dim_product`, `dim_geography`, `dim_ship_mode`. Columns
  mirror the Superstore.csv header exactly (Order ID, Ship Mode, Customer ID,
  Segment, Region, Product ID, Category, Sub-Category, Sales, Discount,
  Profit, etc.), with surrogate keys (`*_key`) generated via `BIGSERIAL`.
- `Superstore.csv` — source data, one row per order line.
- `etl_process.py` — extract/transform/load script. Reads the CSV, dedupes,
  and populates dimensions before the fact table, batching inserts (1000 rows)
  with `ON CONFLICT DO NOTHING` for idempotency.
- `etl_process2.py` — a second, independent ETL that parses
  `product_search.txt` (a markdown-formatted product intelligence report,
  originally gathered via a Brave Search MCP server) and loads it into a
  `dim_product_recommendations` table, matching products by description
  against `dim_product`.

### Known schema/script mismatch

`etl_process.py` currently reads columns from an earlier "Online Retail"
dataset (`StockCode`, `Description`, `CustomerID`, `InvoiceDate`, `InvoiceNo`,
`UnitPrice`) and writes to dimension/fact column names (`stock_code`,
`total_amount`, etc.) that do not exist in the current `schema.sql`/
`Superstore.csv`. It also never populates `dim_geography` or `dim_ship_mode`,
which `fact_sales` requires (`NOT NULL` FKs). Similarly, `dim_product_recommendations`
(used by `etl_process2.py`) is not defined in `schema.sql`. Before running
either script against the current schema, `etl_process.py` needs to be
rewritten to match the Superstore column names/star schema in `schema.sql`,
and the recommendations table needs to be added to `schema.sql`.

### Gemini CLI history

This project was originally built interactively with the Gemini CLI
(`.gemini/settings.json` configures `superset-mcp` and `brave-search` MCP
servers). `README.md` retains the full prompt history used to design the
schema, build the ETL, wire up Superset dashboards, and gather product
intelligence — useful context if extending the dashboard or ETL further, but
describes the older Online Retail dataset in places, not the current
Superstore-based state of `schema.sql`.
