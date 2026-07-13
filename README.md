# Online Retail Data Warehouse ETL

This project implements a Star Schema data warehouse using PostgreSQL and a Python-based ETL process for the "Online Retail" dataset.
xFmCdJICOySrlGes

## Project Structure

- `OnlineRetail.csv`: Source dataset containing transactions.
- `etl_process.py`: Main ETL script (Extract, Transform, Load).
- `.env`: Database connection credentials.
- `requirements.txt`: Python dependencies.

## Star Schema Design

The data is organized into a Star Schema for optimized analytical querying:

- **Fact Table**: `fact_sales` (measures: quantity, unit_price, total_amount)
- **Dimension Tables**:
  - `dim_product`: Product descriptions and stock codes.
  - `dim_customer`: Customer IDs and geographical information.
  - `dim_date`: Granular time dimension (year, month, day, quarter, hour, day of week).

## Prerequisites

- Python 3.10+
- PostgreSQL database
- Virtual environment (recommended)

## Setup Instructions

1. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   Create a `.env` file in the root directory with your PostgreSQL credentials:

   ```env
   POSTGRES_HOST=your_host
   POSTGRES_PORT=5432
   POSTGRES_DATABASE=online-retail-dw
   POSTGRES_USER=your_user
   POSTGRES_PASSWORD=your_password
   ```

3. **Run ETL Process**:
   Execute the Python script to clean the data and populate the database:
   ```bash
   python etl_process.py
   ```

## Built with Gemini CLI

This project was developed using the Gemini CLI with the PostgreSQL extension.

### PostgreSQL Extension Configuration

The Gemini CLI uses the following environment variables to interact with the database. These should be set in your terminal session or stored in a `.env` file (the CLI automatically detects local `.env` files).

```bash
export POSTGRES_HOST="your-db-host"
export POSTGRES_PORT="5432"
export POSTGRES_DATABASE="online-retail-dw"
export POSTGRES_USER="your-user"
export POSTGRES_PASSWORD="your-password"
```

### Example Development Prompts

Here is the sequence of prompts used to generate this project:

#### 1. Data Analysis & Schema Generation

- `analyze first 5 lines of the @OnlineRetail.csv file and create me a start schema for the data warehouse. create dim_product, dim_date, dim_customer and fact_sales tables.`
- `implement this schema using postgres extension`
- `generate a python ETL script named etl_process.py that uses pandas and psycopg2 to load OnlineRetail.csv into the postgres tables. handle deduplication, null customer IDs, and use surrogate keys for the fact table. implement batching and idempotency with ON CONFLICT.`

#### 2. Superset Dashboard Implementation

- `use superset mcp and list me datasources avaiable`
- `I want you to use superset MCP server to connect to superset. Analyze database Online-Retail-DW and generate me a plan for executive dashboard design`
- `Dont use @OnlineRetail.csv use online-retail-dw database where data is loaded. I want you to design dashboard with postgress connection and SQL queries there`
- `Use this plan and implement this dashboard in apache superset via MCP`
- `the chart revenue by country is not rendering its throwing error An error occurred while rendering the visualization: Error: Item with key "bar" is not registered.`
- `can you fix Hourly Sales Volume chart to use x-axis hour`
- `fix revenue by country chart to use map to show amounts per countries`
- `fix the chart "Top 10 Products by Revenue" to use horizontal bar chart.`
- `I got this error "Duplicate column/metric labels: "product_description". Please make sure all columns and metrics have a unique label."`
- `create me a chart of treemap for products distribution in online retail datasource using apache superset mcp`
- `update readme.md file with all prompts used in this conversation`

#### 3. Data Lake Implementation

- I want to expand online-retail-dw with additional table that provides info to the dim_products table. New table should contain reference to product, date and recommendation columns.
  Use postgress MCP to upgrade the databse structure

- for top 10 selling products in dim_products table do a search on web using brave search api mcp server and gather intelligence about them. Save the results into product_search.txt  
   file

- use the @product_search.txt and create etl_process2.py script that will load the recommedations from the txt file into dim_product_recommendations table. If there is missing data do
  another brave search to gather all necessary intelligence.
-

## Key Features

- **Idempotent Loads**: Uses `ON CONFLICT` clauses to prevent duplicate data if the script is run multiple times.
- **Data Cleaning**: Handles missing customer IDs, deduplicates records, and calculates `total_amount`.
- **Batch Processing**: Inserts data in batches of 1000 rows for better performance and memory management.
