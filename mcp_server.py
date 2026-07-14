"""MCP server exposing the Supabase-hosted Superstore data warehouse schema to Claude.

Provides schema-introspection tools (list_tables, describe_table, get_schema) and a
guarded, read-only SQL execution tool (run_query) scoped to the public schema. The
SYSTEM_INSTRUCTIONS constant is surfaced to the client both as the server's MCP
"instructions" (sent at session init) and as an explicit `sql_generation_guidelines`
prompt, so the policy travels with the tools regardless of which client connects.
"""
import datetime
import logging
import os
import re
from contextlib import contextmanager
from decimal import Decimal

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("supabase-schema-mcp")

DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_SCHEMA = "public"
DEFAULT_ROW_LIMIT = 100
MAX_ROW_LIMIT = 1000
STATEMENT_TIMEOUT_MS = 8000

# Supabase-managed schemas that hold credentials, tokens, and other data this
# tool must never touch, even if a query only reads from them.
FORBIDDEN_SCHEMAS = (
    "auth", "storage", "vault", "pgsodium", "extensions",
    "realtime", "supabase_functions", "pg_catalog", "information_schema",
    "graphql", "graphql_public", "net", "cron",
)

WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|"
    r"call|do|vacuum|refresh|listen|notify|execute|merge|lock|comment|"
    r"reindex|cluster|security|into)\b",
    re.IGNORECASE,
)

IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

SYSTEM_INSTRUCTIONS = """\
You are querying a Supabase-hosted PostgreSQL data warehouse (a Superstore
sales star schema) through the supabase-schema MCP server. Follow these rules
whenever you generate or execute SQL with these tools:

1. Discover before you write SQL.
   Never guess table or column names. Call `list_tables` and `describe_table`
   (or `get_schema` for the whole model) before writing a query unless you
   already confirmed the exact schema earlier in this session. Treat that
   output as the source of truth over any CSV header, README, or memory of a
   similar-looking dataset.

2. Scope: public schema only.
   Only query objects in the `public` schema. Never reference `auth`,
   `storage`, `vault`, `pgsodium`, `extensions`, `realtime`, or any other
   Supabase-internal schema, even if asked — they hold credentials and PII
   that are out of bounds for this tool. `run_query` rejects these
   server-side; do not try to route around the rejection (e.g. via
   `search_path`, quoted identifiers, or `pg_catalog` introspection).

3. Read-only, always, one statement at a time.
   Only `SELECT` and read-only `WITH ... SELECT` statements are permitted.
   Never attempt INSERT/UPDATE/DELETE/TRUNCATE/DROP/ALTER/CREATE or any other
   write/DDL — the underlying connection is opened as a read-only Postgres
   transaction, so these fail at the database level regardless, but do not
   attempt them "to see what happens". Submit exactly one statement per call;
   never chain statements with `;`.

4. Query shape.
   Qualify tables as `public.<table>`. Join `fact_sales` to dimension tables
   on the surrogate `*_key` columns, not on business keys (`product_id`,
   `customer_id`, etc.) unless the task is specifically to validate those
   business keys. Avoid `SELECT *` on `fact_sales`; select only the columns
   needed to answer the question. Always include a `LIMIT` on row-level or
   exploratory queries — the tool defaults to 100 rows and hard-caps at 1000
   regardless of what you request. Bounded aggregates (COUNT, SUM, GROUP BY
   producing a small result set) don't need one.

5. User-supplied values.
   Never splice raw user text into a string literal without escaping
   embedded single quotes (`'` -> `''`). Validate that a value that should be
   numeric or a date actually looks like one before inlining it.

6. Errors and ambiguity.
   If a query errors, read the message and fix the actual cause (wrong
   column, type mismatch, bad join) — don't retry the identical query, and
   don't silently drop a WHERE/JOIN clause just to make it succeed. If a
   request is ambiguous (e.g. "top products" with no metric or time range
   given), state the assumption you're making rather than picking one
   silently.

7. Results.
   Summarize results in natural language for the person you're helping;
   don't dump raw rows/JSON unless they asked for the raw data.
"""


@contextmanager
def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set — check your .env file.")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        # Hard guarantee: any write inside this transaction is rejected by
        # Postgres itself, independent of the keyword/schema checks below.
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cur.execute(f"SET search_path = {ALLOWED_SCHEMA}")
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _jsonable(value):
    """Coerces psycopg2 result values into JSON-serializable primitives."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _jsonable_rows(rows):
    return [{k: _jsonable(v) for k, v in row.items()} for row in rows]


def _validate_query(sql: str) -> str:
    """Raises ValueError unless sql is a single, public-schema-only, read-only statement."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise ValueError("Empty query.")
    if ";" in stripped:
        raise ValueError("Only a single statement is allowed (no ';'-chained statements).")
    if not re.match(r"^(select|with)\b", stripped, re.IGNORECASE):
        raise ValueError("Only SELECT (or WITH ... SELECT) statements are allowed.")
    if WRITE_KEYWORDS.search(stripped):
        raise ValueError("Query contains a disallowed write/DDL keyword.")
    for schema in FORBIDDEN_SCHEMAS:
        if re.search(rf'\b{schema}\b"?\s*\.', stripped, re.IGNORECASE):
            raise ValueError(f"Access to the '{schema}' schema is not permitted through this tool.")
    return stripped


mcp = FastMCP("supabase-schema", instructions=SYSTEM_INSTRUCTIONS)


@mcp.tool()
def list_tables() -> list[dict]:
    """List every table in the public schema with its approximate row count."""
    query = """
        SELECT c.relname AS table_name, c.reltuples::bigint AS approx_row_count
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
        ORDER BY c.relname;
    """
    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        return cur.fetchall()


@mcp.tool()
def describe_table(table_name: str) -> dict:
    """Return columns (name/type/nullability/default), primary keys, and foreign keys for a public-schema table."""
    if not IDENTIFIER_RE.match(table_name):
        raise ValueError("Invalid table name.")

    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
            """,
            (table_name,),
        )
        columns = cur.fetchall()
        if not columns:
            raise ValueError(f"Table '{table_name}' not found in the public schema.")

        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public' AND tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY';
            """,
            (table_name,),
        )
        primary_keys = [r["column_name"] for r in cur.fetchall()]

        cur.execute(
            """
            SELECT kcu.column_name, ccu.table_name AS references_table, ccu.column_name AS references_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
            WHERE tc.table_schema = 'public' AND tc.table_name = %s AND tc.constraint_type = 'FOREIGN KEY';
            """,
            (table_name,),
        )
        foreign_keys = cur.fetchall()

    return {
        "table_name": table_name,
        "columns": columns,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
    }


@mcp.tool()
def get_schema() -> dict:
    """Return the full public-schema data model: every table with its columns and foreign keys."""
    return {"tables": [describe_table(t["table_name"]) for t in list_tables()]}


@mcp.tool()
def run_query(sql: str, row_limit: int = DEFAULT_ROW_LIMIT) -> dict:
    """
    Execute a single read-only SELECT/WITH query against the public schema and return rows.

    Rejects anything but a single SELECT/WITH statement, any write/DDL keyword, and
    any reference to non-public schemas, before the query reaches the database. The
    connection itself is also opened as a read-only Postgres transaction, so this
    is enforced at two independent layers. Results are capped at `row_limit`
    (default 100, hard max 1000).
    """
    try:
        validated = _validate_query(sql)
    except ValueError as e:
        return {"error": str(e)}

    limit = max(1, min(int(row_limit), MAX_ROW_LIMIT))

    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        try:
            cur.execute(validated)
        except Exception as e:
            return {"error": str(e), "query": validated}

        total = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else None
        rows = _jsonable_rows(cur.fetchmany(limit))

    return {
        "returned_rows": len(rows),
        "total_rows_available": total,
        "truncated": bool(total is not None and total > limit),
        "rows": rows,
    }


@mcp.prompt()
def sql_generation_guidelines() -> str:
    """The SQL-generation policy this server expects callers to follow."""
    return SYSTEM_INSTRUCTIONS


@mcp.resource("schema://public")
def public_schema_resource() -> str:
    """Full JSON description of the public schema's tables, columns, and foreign keys."""
    import json

    return json.dumps(get_schema(), default=str, indent=2)


if __name__ == "__main__":
    mcp.run()
