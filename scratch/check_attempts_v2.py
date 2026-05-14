import sqlite3
conn = sqlite3.connect('production.db')
cursor = conn.cursor()
cursor.execute("""
    SELECT a.id, a.user_id, a.status, r.id as report_id, r.total_score, r.correct_count, r.incorrect_count, r.unattempted_count
    FROM attempts a 
    LEFT JOIN reports r ON a.id = r.attempt_id 
    ORDER BY a.start_time DESC LIMIT 5;
""")
rows = cursor.fetchall()
for row in rows:
    print(f"Attempt ID: {row[0]}, User: {row[1]}, Status: {row[2]}, Report: {row[3]}, Score: {row[4]}, C: {row[5]}, I: {row[6]}, S: {row[7]}")
conn.close()
