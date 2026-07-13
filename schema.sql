CREATE TABLE dim_date (
  date_key        INTEGER PRIMARY KEY,   -- YYYYMMDD
  full_date       DATE NOT NULL UNIQUE,
  day_of_month    SMALLINT,
  month_num       SMALLINT,
  month_name      VARCHAR(20),
  quarter_num     SMALLINT,
  year_num        SMALLINT,
  week_of_year    SMALLINT
);

CREATE TABLE dim_customer (
  customer_key    BIGSERIAL PRIMARY KEY,
  customer_id     VARCHAR(20) NOT NULL UNIQUE,
  customer_name   VARCHAR(255) NOT NULL,
  segment         VARCHAR(50) NOT NULL
);

CREATE TABLE dim_product (
  product_key     BIGSERIAL PRIMARY KEY,
  product_id      VARCHAR(30) NOT NULL UNIQUE,
  product_name    VARCHAR(500) NOT NULL,
  sub_category    VARCHAR(100) NOT NULL,
  category        VARCHAR(100) NOT NULL
);

CREATE TABLE dim_geography (
  geography_key   BIGSERIAL PRIMARY KEY,
  country         VARCHAR(100) NOT NULL,
  region          VARCHAR(50) NOT NULL,
  state           VARCHAR(100) NOT NULL,
  city            VARCHAR(100) NOT NULL,
  postal_code     VARCHAR(20)
);

CREATE TABLE dim_ship_mode (
  ship_mode_key   SMALLSERIAL PRIMARY KEY,
  ship_mode       VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE fact_sales (
  sales_fact_id   BIGSERIAL PRIMARY KEY,
  row_id          INTEGER NOT NULL,
  order_id        VARCHAR(30) NOT NULL,
  order_date_key  INTEGER NOT NULL REFERENCES dim_date(date_key),
  ship_date_key   INTEGER NOT NULL REFERENCES dim_date(date_key),
  customer_key    BIGINT NOT NULL REFERENCES dim_customer(customer_key),
  product_key     BIGINT NOT NULL REFERENCES dim_product(product_key),
  geography_key   BIGINT NOT NULL REFERENCES dim_geography(geography_key),
  ship_mode_key   SMALLINT NOT NULL REFERENCES dim_ship_mode(ship_mode_key),
  sales           NUMERIC(12,4) NOT NULL,
  quantity        INTEGER NOT NULL,
  discount        NUMERIC(6,4) NOT NULL,
  profit          NUMERIC(12,4) NOT NULL
);

CREATE UNIQUE INDEX ux_fact_sales_row_id ON fact_sales(row_id);
CREATE INDEX ix_fact_sales_order_id ON fact_sales(order_id);