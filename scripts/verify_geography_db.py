import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "production.db"

def main():
    print(f"Connecting to database: {DB_PATH}")
    if not DB_PATH.exists():
        print("ERROR: Database file not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check overall counts
        cursor.execute("SELECT count(*) FROM gs_lms_syllabus_nodes")
        node_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT count(*) FROM gs_lms_content_sections")
        section_count = cursor.fetchone()[0]

        print(f"\nOverall Database Counts:")
        print(f"  gs_lms_syllabus_nodes: {node_count}")
        print(f"  gs_lms_content_sections: {section_count}")

        # Check by node type
        cursor.execute("SELECT node_type, count(*) FROM gs_lms_syllabus_nodes GROUP BY node_type")
        print("\nNodes by type:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")

        # Check details of Leaf topics
        cursor.execute("SELECT id, title FROM gs_lms_syllabus_nodes WHERE node_type = 'LEAF_TOPIC'")
        leaves = cursor.fetchall()
        print(f"\nLeaf Nodes Count: {len(leaves)}")

        # Verify content sections per leaf
        missing_sections = []
        for leaf_id, title in leaves:
            cursor.execute("SELECT section_label FROM gs_lms_content_sections WHERE syllabus_node_id = ?", (leaf_id,))
            labels = [r[0] for r in cursor.fetchall()]
            expected = {'BASIC', 'ADVANCED', 'NCERT_LEVEL', 'EXAMINER_TRAPS'}
            missing = expected - set(labels)
            if missing:
                missing_sections.append((title, missing))

        if missing_sections:
            print("\nWARNING: Some leaf nodes are missing expected content sections:")
            for title, missing in missing_sections:
                print(f"  - {title}: missing {missing}")
        else:
            print("\nSuccess: All leaf nodes have the complete 4-section set (BASIC, ADVANCED, NCERT_LEVEL, EXAMINER_TRAPS).")

        # Display a sample from a content section
        print("\nDisplaying a sample content section (BASIC of Lecture 8 if available):")
        import json
        cursor.execute("""
            SELECT cs.blocks 
            FROM gs_lms_content_sections cs
            JOIN gs_lms_syllabus_nodes n ON cs.syllabus_node_id = n.id
            WHERE n.title LIKE '%Lecture 8%' AND cs.section_label = 'BASIC'
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row and row[0]:
            blocks = json.loads(row[0])
            for idx, block in enumerate(blocks[:2]):
                print(f"  Paragraph {idx+1}: {block.get('text', '')[:150]}...")
        else:
            print("  No sample found for Lecture 8 BASIC.")

    except Exception as e:
        print(f"ERROR: Verification failed with exception: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
