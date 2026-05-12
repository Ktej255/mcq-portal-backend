import psycopg2
import os

url = os.environ.get('DATABASE_URL')
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
cols = [c[0] for c in cur.fetchall()]
print(f"Columns in users: {cols}")

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
tables = [t[0] for t in cur.fetchall()]
print(f"Tables: {tables}")
conn.close()
