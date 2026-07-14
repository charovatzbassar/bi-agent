"""Golden-query regression suite for the supabase-schema MCP server.

Each entry pairs a natural-language question with the canonical SQL that
answers it against the Superstore star schema. Running this file executes
every `expected_sql` through the same read-only path as the `run_query` MCP
tool, to confirm the queries still match the current schema/data and to
print the ground-truth result each one produces.

To grade an agent's generated SQL for one of these questions, pass its SQL
to `check_candidate(entry, candidate_sql)` — it re-runs the golden SQL, runs
the candidate, and compares the two result sets (order-independent).
"""
import json

import mcp_server as srv

GOLDEN_QUERIES = [
    {
        "id": "consumer_segment_count",
        "question": "How many customers are in the Consumer segment?",
        "expected_sql": """
            SELECT COUNT(*) AS customer_count
            FROM public.dim_customer
            WHERE segment = 'Consumer'
        """,
        "tests": "single-table filter + COUNT",
    },
    {
        "id": "sales_profit_by_category",
        "question": "What is the total sales and profit for each product category?",
        "expected_sql": """
            SELECT p.category, SUM(f.sales) AS total_sales, SUM(f.profit) AS total_profit
            FROM public.fact_sales f
            JOIN public.dim_product p ON f.product_key = p.product_key
            GROUP BY p.category
            ORDER BY total_sales DESC
        """,
        "tests": "fact-to-dim join + GROUP BY + multiple aggregates",
    },
    {
        "id": "top5_products_by_profit",
        "question": "Which 5 products generated the most total profit?",
        "expected_sql": """
            SELECT p.product_name, SUM(f.profit) AS total_profit
            FROM public.fact_sales f
            JOIN public.dim_product p ON f.product_key = p.product_key
            GROUP BY p.product_name
            ORDER BY total_profit DESC
            LIMIT 5
        """,
        "tests": "join + GROUP BY + ORDER BY + LIMIT (top-N)",
    },
    {
        "id": "sales_by_region",
        "question": "What is the total sales by region?",
        "expected_sql": """
            SELECT g.region, SUM(f.sales) AS total_sales
            FROM public.fact_sales f
            JOIN public.dim_geography g ON f.geography_key = g.geography_key
            GROUP BY g.region
            ORDER BY total_sales DESC
        """,
        "tests": "join to a different dimension + GROUP BY",
    },
    {
        "id": "same_day_orders",
        "question": "How many distinct orders were shipped Same Day?",
        "expected_sql": """
            SELECT COUNT(DISTINCT f.order_id) AS order_count
            FROM public.fact_sales f
            JOIN public.dim_ship_mode sm ON f.ship_mode_key = sm.ship_mode_key
            WHERE sm.ship_mode = 'Same Day'
        """,
        "tests": "join + COUNT DISTINCT (order vs. line-item granularity)",
    },
    {
        "id": "loss_making_line_items",
        "question": "How many order line items resulted in a loss (negative profit)?",
        "expected_sql": "SELECT COUNT(*) AS loss_making_lines FROM public.fact_sales WHERE profit < 0",
        "tests": "fact-table-only filter, no joins needed",
    },
    {
        "id": "sales_by_order_year",
        "question": "What was the total sales in 2016, based on order date?",
        "expected_sql": """
            SELECT SUM(f.sales) AS total_sales
            FROM public.fact_sales f
            JOIN public.dim_date d ON f.order_date_key = d.date_key
            WHERE d.year_num = 2016
        """,
        "tests": "join to dim_date on order_date_key specifically, not ship_date_key",
    },
    {
        "id": "avg_discount_by_segment",
        "question": "Which customer segment has the highest average discount?",
        "expected_sql": """
            SELECT c.segment, AVG(f.discount) AS avg_discount
            FROM public.fact_sales f
            JOIN public.dim_customer c ON f.customer_key = c.customer_key
            GROUP BY c.segment
            ORDER BY avg_discount DESC
            LIMIT 1
        """,
        "tests": "join + GROUP BY + AVG + top-1",
    },
    {
        "id": "catalog_product_count_trap",
        "question": "How many products does the catalog have?",
        "expected_sql": "SELECT COUNT(*) AS product_count FROM public.dim_product",
        "tests": (
            "schema-discipline trap: catalog size (all of dim_product) is a "
            "different number from products actually sold (DISTINCT product_key "
            "in fact_sales) - checks the agent doesn't conflate the two"
        ),
    },
]


def _normalize(rows):
    """Row-order- and key-order-independent representation for comparison."""
    return sorted(tuple(sorted(row.items())) for row in rows)


def run_golden(entry):
    result = srv.run_query(entry["expected_sql"], row_limit=srv.MAX_ROW_LIMIT)
    if "error" in result:
        raise AssertionError(f"[{entry['id']}] golden SQL failed: {result['error']}")
    return result["rows"]


def check_candidate(entry, candidate_sql):
    """Runs candidate_sql and reports whether its result set matches the golden result."""
    golden_rows = run_golden(entry)
    candidate_result = srv.run_query(candidate_sql, row_limit=srv.MAX_ROW_LIMIT)
    if "error" in candidate_result:
        return {"passed": False, "reason": candidate_result["error"]}

    passed = _normalize(golden_rows) == _normalize(candidate_result["rows"])
    return {"passed": passed, "golden_rows": golden_rows, "candidate_rows": candidate_result["rows"]}


def main():
    print(f"Running {len(GOLDEN_QUERIES)} golden queries against the live schema...\n")
    failures = 0
    for entry in GOLDEN_QUERIES:
        try:
            rows = run_golden(entry)
            preview = json.dumps(rows[:3], default=str)
            print(f"PASS  {entry['id']:<28} rows={len(rows):<4} {preview}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {entry['id']:<28} {e}")

    print(f"\n{len(GOLDEN_QUERIES) - failures}/{len(GOLDEN_QUERIES)} golden queries executed successfully.")


if __name__ == "__main__":
    main()
