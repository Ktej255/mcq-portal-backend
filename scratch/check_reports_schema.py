import sqlite3
conn = sqlite3.connect('production.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(reports);")
cols = cursor.fetchall()
for col in cols:
    print(col)
conn.close()
