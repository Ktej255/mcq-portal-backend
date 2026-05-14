
import sqlite3
import os

db_path = "d:/Development/MCQ Portal/backend/production.db"
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- TESTS ---")
cursor.execute("SELECT id, title, is_active FROM tests")
for row in cursor.fetchall():
    print(row)

print("\n--- SUBJECTS ---")
cursor.execute("SELECT id, name FROM subjects")
for row in cursor.fetchall():
    print(row)

conn.close()
