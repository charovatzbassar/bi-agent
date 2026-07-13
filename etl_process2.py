import psycopg2
from psycopg2.extras import execute_values
import os
import re
import logging
from datetime import date
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_connection():
    """Establishes a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DATABASE"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )

def parse_product_search(file_path):
    """Parses the product_search.txt file to extract recommendations."""
    recommendations = []
    current_product = None
    current_details = []
    
    with open(file_path, 'r') as f:
        content = f.read()
        
    # Split by product sections (### followed by number and product name)
    sections = re.split(r'### \d+\. ', content)
    
    for section in sections[1:]: # Skip the header
        lines = section.strip().split('\n')
        if not lines:
            continue
            
        product_name = lines[0].strip()
        # Combine all following bullet points into a single recommendation text
        details = " ".join([line.strip().lstrip('- ') for line in lines[1:] if line.strip()])
        
        recommendations.append({
            'product_description': product_name,
            'recommendation_text': details
        })
        
    return recommendations

def run_recommendations_etl():
    logging.info("Starting Recommendations ETL process...")
    
    file_path = 'product_search.txt'
    if not os.path.exists(file_path):
        logging.error(f"File {file_path} not found.")
        return

    parsed_data = parse_product_search(file_path)
    if not parsed_data:
        logging.info("No recommendations found in file.")
        return

    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Fetch product map to get product_key from description
        cur.execute("SELECT product_key, description FROM public.dim_product")
        prod_map = {row[1].strip(): row[0] for row in cur.fetchall()}
        
        final_data = []
        today = date.today()
        rec_type = "Web Intelligence"
        
        for item in parsed_data:
            desc = item['product_description']
            # Match description exactly or as a substring if needed
            # In our case, the descriptions in product_search.txt match dim_product
            prod_key = prod_map.get(desc)
            
            if prod_key:
                final_data.append((
                    prod_key,
                    today,
                    item['recommendation_text'],
                    rec_type
                ))
            else:
                logging.warning(f"Product '{desc}' not found in dim_product table.")

        if final_data:
            query = """
                INSERT INTO public.dim_product_recommendations 
                (product_key, recommendation_date, recommendation_text, recommendation_type)
                VALUES %s
                ON CONFLICT (product_key, recommendation_date, recommendation_type) DO NOTHING
            """
            execute_values(cur, query, final_data)
            logging.info(f"Successfully processed {len(final_data)} recommendations.")
        
        conn.commit()
        logging.info("Recommendations ETL completed successfully.")
        
    except Exception as e:
        conn.rollback()
        logging.error(f"An error occurred: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_recommendations_etl()
