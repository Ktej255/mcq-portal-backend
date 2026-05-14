import sqlite3
import os

db_path = "d:/Development/MCQ Portal/backend/production.db"
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT id, title FROM tests")
rows = cursor.fetchall()

print("Tests in DB:")
for row in rows:
    print(f"ID: {row[0]}, Title: '{row[1]}'")

conn.close()
