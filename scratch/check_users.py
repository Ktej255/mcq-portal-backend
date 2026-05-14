import sqlite3
conn = sqlite3.connect('production.db')
cursor = conn.cursor()
cursor.execute("SELECT id, email, full_name FROM users;")
rows = cursor.fetchall()
for row in rows:
    print(f"ID: {row[0]}, Email: {row[1]}, Name: {row[2]}")
conn.close()
