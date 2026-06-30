import sqlite3
conn = sqlite3.connect('production.db')
conn.execute("PRAGMA foreign_keys=OFF")
# Identify orphan leaf nodes (subject 1, LEAF_TOPIC, no content sections)
orphan_ids = [r[0] for r in conn.execute("""
SELECT n.id FROM gs_lms_syllabus_nodes n
WHERE n.subject_id=1 AND n.node_type='LEAF_TOPIC'
AND NOT EXISTS (SELECT 1 FROM gs_lms_content_sections s WHERE s.syllabus_node_id=n.id)
""")]
print(f"Deleting {len(orphan_ids)} orphan leaf nodes...")
# Clean dependent student/progress rows that reference these nodes (local DB hygiene)
dep_tables = [
    ("gs_lms_funnel_progress", "syllabus_node_id"),
    ("gs_lms_video_watches", "syllabus_node_id"),
    ("gs_lms_revisit_schedule", "syllabus_node_id"),
    ("gs_lms_reading_times", "syllabus_node_id"),
    ("gs_lms_recall_attempts", "syllabus_node_id"),
]
for tbl, col in dep_tables:
    try:
        conn.executemany(f"DELETE FROM {tbl} WHERE {col}=?", [(i,) for i in orphan_ids])
    except sqlite3.OperationalError:
        pass
conn.executemany("DELETE FROM gs_lms_syllabus_nodes WHERE id=?", [(i,) for i in orphan_ids])
conn.commit()
total = conn.execute("SELECT COUNT(*) FROM gs_lms_syllabus_nodes WHERE subject_id=1").fetchone()[0]
lectures = conn.execute("SELECT COUNT(*) FROM gs_lms_syllabus_nodes WHERE subject_id=1 AND title LIKE 'Lecture%'").fetchone()[0]
print(f"Remaining subject-1 nodes: {total} | still 'Lecture...': {lectures}")
conn.close()
