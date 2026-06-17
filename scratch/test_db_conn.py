import urllib.parse
from sqlalchemy import create_engine
import httpx

# 1. Credentials
username = "postgres.ezoxfuxdtqgykhxoteii"
password = "/t5@x&HmdR-V8SN"
host = "aws-1-ap-northeast-1.pooler.supabase.com"  # Updated to aws-1
port = "5432"
dbname = "postgres"
tablename = "letter_scores"
session_id = "e6c585cb-765f-48b1-b172-fcef3258de8c"

encoded_user = urllib.parse.quote_plus(username)
encoded_pass = urllib.parse.quote_plus(password)

connection_string = f"postgresql://{encoded_user}:{encoded_pass}@{host}:{port}/{dbname}"
print("Connection String constructed:")
print(connection_string.replace(password, "********"))

# 2. Test SQLAlchemy connection
print("\nTesting connection via SQLAlchemy directly...")
try:
    engine = create_engine(connection_string)
    with engine.connect() as conn:
        print("SQLAlchemy connected successfully!")
        # Try to query the table
        res = conn.execute(f'SELECT * FROM "{tablename}" LIMIT 5')
        print("QueryResult:", res.fetchall())
except Exception as e:
    print("SQLAlchemy connection failed:", e)

# 3. Call local FastAPI endpoint
print("\nTriggering Connect DB API locally...")
url = f"http://localhost:8000/api/sessions/{session_id}/connect-db"
payload = {
    "connection_string": connection_string,
    "table_name": tablename
}
try:
    r = httpx.post(url, json=payload, timeout=10.0)
    print(f"API Response Code: {r.status_code}")
    print(f"API Response Body: {r.text}")
except Exception as e:
    print("Failed to call API:", e)
