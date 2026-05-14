import sqlite3
conn = sqlite3.connect('production.db')
cursor = conn.cursor()
cursor.execute("SELECT id, title FROM tests WHERE title LIKE '%Environment Batch 1%';")
rows = cursor.fetchall()
for row in rows:
    print(f"ID: {row[0]}, Title: {row[1]}")
conn.close()
