import sqlite3
import pandas as pd
import os

db_name = "test_analytics.db"
db_path = os.path.abspath(db_name)

print("Creating mock letter scores dataset...")
# Create a-z, A-Z mapping
letters = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
values = list(range(1, 53))

df = pd.DataFrame({
    "Letter": letters,
    "Value": values
})

print(f"Connecting to database at: {db_path}")
conn = sqlite3.connect(db_path)

print("Writing table 'letter_scores'...")
df.to_sql("letter_scores", conn, index=False, if_exists="replace")

# Verify the table exists
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:", [t[0] for t in tables])

# Show sample rows
cursor.execute("SELECT * FROM letter_scores LIMIT 5;")
print("Sample rows:", cursor.fetchall())

conn.close()
print("Database created successfully!")
