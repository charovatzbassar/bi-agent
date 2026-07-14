import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_connection():
    """Establishes a connection to the PostgreSQL database."""
    return psycopg2.connect(
        os.getenv("DATABASE_URL")
    )

def insert_batches(cur, query, data, batch_size=1000, table_name=""):
    """Inserts data in batches and logs progress."""
    total = len(data)
    if total == 0:
        logging.info(f"No data to insert into {table_name}.")
        return

    for i in range(0, total, batch_size):
        batch = data[i:i + batch_size]
        execute_values(cur, query, batch)
        logging.info(f"Inserted {min(i + batch_size, total)}/{total} rows into {table_name}")

def build_date_rows(dates):
    """Builds dim_date rows for a collection of unique timestamps."""
    rows = []
    for d in dates:
        rows.append((
            int(d.strftime('%Y%m%d')),
            d.date(),
            d.day,
            d.month,
            d.strftime('%B'),
            (d.month - 1) // 3 + 1,
            d.year,
            int(d.isocalendar()[1]),
        ))
    return rows

def run_etl():
    logging.info("Starting ETL process...")

    # 1. Load Source Data
    df = pd.read_csv('Superstore.csv', encoding='ISO-8859-1')

    # 2. Deduplication & Cleaning
    df = df.drop_duplicates()
    df['Order Date'] = pd.to_datetime(df['Order Date'], format='%m/%d/%Y')
    df['Ship Date'] = pd.to_datetime(df['Ship Date'], format='%m/%d/%Y')
    # Zero-pad US zip codes so leading zeros survive as text (e.g. Boston 02116).
    df['Postal Code'] = df['Postal Code'].apply(lambda z: f"{int(z):05d}")

    conn = get_connection()
    cur = conn.cursor()

    try:
        # 3. Populate Dimension: dim_customer
        customers = df[['Customer ID', 'Customer Name', 'Segment']].drop_duplicates(subset=['Customer ID'])
        insert_batches(cur, """
            INSERT INTO public.dim_customer (customer_id, customer_name, segment)
            VALUES %s
            ON CONFLICT (customer_id) DO NOTHING
        """, customers.values.tolist(), table_name="dim_customer")

        # 4. Populate Dimension: dim_product
        # A handful of Product IDs map to more than one Product Name in the source
        # data; product_id is unique in dim_product, so we keep the first name seen.
        products = df[['Product ID', 'Product Name', 'Sub-Category', 'Category']].drop_duplicates(subset=['Product ID'])
        insert_batches(cur, """
            INSERT INTO public.dim_product (product_id, product_name, sub_category, category)
            VALUES %s
            ON CONFLICT (product_id) DO NOTHING
        """, products.values.tolist(), table_name="dim_product")

        # 5. Populate Dimension: dim_geography
        geography = df[['Country', 'Region', 'State', 'City', 'Postal Code']].drop_duplicates()
        insert_batches(cur, """
            INSERT INTO public.dim_geography (country, region, state, city, postal_code)
            VALUES %s
            ON CONFLICT (country, region, state, city, postal_code) DO NOTHING
        """, geography.values.tolist(), table_name="dim_geography")

        # 6. Populate Dimension: dim_ship_mode
        ship_modes = df[['Ship Mode']].drop_duplicates()
        insert_batches(cur, """
            INSERT INTO public.dim_ship_mode (ship_mode)
            VALUES %s
            ON CONFLICT (ship_mode) DO NOTHING
        """, ship_modes.values.tolist(), table_name="dim_ship_mode")

        # 7. Populate Dimension: dim_date (built from both order and ship dates)
        all_dates = pd.concat([df['Order Date'], df['Ship Date']]).drop_duplicates()
        insert_batches(cur, """
            INSERT INTO public.dim_date (date_key, full_date, day_of_month, month_num, month_name, quarter_num, year_num, week_of_year)
            VALUES %s
            ON CONFLICT (full_date) DO NOTHING
        """, build_date_rows(all_dates), table_name="dim_date")

        # 8. Prepare and Populate Fact: fact_sales
        # Fetch surrogate keys to map business keys to IDs
        cur.execute("SELECT customer_key, customer_id FROM public.dim_customer")
        cust_map = {row[1]: row[0] for row in cur.fetchall()}

        cur.execute("SELECT product_key, product_id FROM public.dim_product")
        prod_map = {row[1]: row[0] for row in cur.fetchall()}

        cur.execute("SELECT geography_key, country, region, state, city, postal_code FROM public.dim_geography")
        geo_map = {(row[1], row[2], row[3], row[4], row[5]): row[0] for row in cur.fetchall()}

        cur.execute("SELECT ship_mode_key, ship_mode FROM public.dim_ship_mode")
        ship_mode_map = {row[1]: row[0] for row in cur.fetchall()}

        cur.execute("SELECT date_key, full_date FROM public.dim_date")
        date_map = {row[1]: row[0] for row in cur.fetchall()}

        # Map keys
        df['customer_key'] = df['Customer ID'].map(cust_map)
        df['product_key'] = df['Product ID'].map(prod_map)
        df['geography_key'] = list(zip(df['Country'], df['Region'], df['State'], df['City'], df['Postal Code']))
        df['geography_key'] = df['geography_key'].map(geo_map)
        df['ship_mode_key'] = df['Ship Mode'].map(ship_mode_map)
        df['order_date_key'] = df['Order Date'].dt.date.map(date_map)
        df['ship_date_key'] = df['Ship Date'].dt.date.map(date_map)

        # Prepare fact table data
        fact_df = df[[
            'Row ID', 'Order ID', 'order_date_key', 'ship_date_key', 'customer_key',
            'product_key', 'geography_key', 'ship_mode_key', 'Sales', 'Quantity', 'Discount', 'Profit'
        ]].copy()
        fact_df = fact_df.dropna()

        # Convert to standard Python types to avoid numpy type issues
        fact_data = []
        for row in fact_df.itertuples(index=False):
            fact_data.append((
                int(row[0]),
                str(row[1]),
                int(row[2]),
                int(row[3]),
                int(row[4]),
                int(row[5]),
                int(row[6]),
                int(row[7]),
                float(row[8]),
                int(row[9]),
                float(row[10]),
                float(row[11]),
            ))

        logging.info(f"Total rows to insert into fact_sales: {len(fact_data)}")

        insert_batches(cur, """
            INSERT INTO public.fact_sales
                (row_id, order_id, order_date_key, ship_date_key, customer_key, product_key, geography_key, ship_mode_key, sales, quantity, discount, profit)
            VALUES %s
            ON CONFLICT (row_id) DO NOTHING
        """, fact_data, table_name="fact_sales")

        conn.commit()
        logging.info("ETL process completed successfully.")

    except Exception as e:
        conn.rollback()
        logging.error(f"An error occurred: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_etl()
