import sqlite3
import os

db_path = "d:/Development/MCQ Portal/backend/production.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
    SELECT t.id, t.title, s.name 
    FROM tests t 
    JOIN subjects s ON t.subject_id = s.id
""")
rows = cursor.fetchall()

print("Tests and Subjects:")
for row in rows:
    print(f"ID: {row[0]}, Title: '{row[1]}', Subject: '{row[2]}'")

conn.close()
