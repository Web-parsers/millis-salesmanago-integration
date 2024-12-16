import json
import os

import psycopg2
from psycopg2.extras import RealDictCursor

from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env.


# Database connection details
DB_CONFIG = {
    "dbname": os.getenv("db_name"),
    "user": os.getenv("db_username"),
    "password": os.getenv("db_password"),
    "host": os.getenv("db_host"),
    "port": os.getenv("db_port"),
}

def get_people_by_phone(phone_number):
    try:
        # Establish a connection to the database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Query to fetch people by phone
        query = """
        SELECT * FROM salesmanago
        WHERE "public"."salesmanago"."Phone" = %s;
        """
        cursor.execute(query, (phone_number,))
        results = cursor.fetchall()

        # Close the connection
        cursor.close()
        conn.close()

        # Return JSON result
        return results

    except Exception as e:
        return json.dumps({"error": str(e)})

# Example usage
if __name__ == "__main__":
    phone = "53856960"  # Replace with the desired phone number
    result = get_people_by_phone(phone)
    print(result)
