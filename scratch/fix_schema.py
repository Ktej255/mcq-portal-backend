import sqlite3

def fix():
    conn = sqlite3.connect('production.db')
    cursor = conn.cursor()
    
    # Add columns to questions if they don't exist
    cols = [
        ('status', "VARCHAR(9) DEFAULT 'PUBLISHED' NOT NULL"),
        ('reviewer_id', "INTEGER"),
        ('explanation_quality_score', "FLOAT"),
        ('is_outdated', "BOOLEAN DEFAULT 0 NOT NULL"),
        ('last_reviewed_at', "DATETIME"),
        ('created_at', "DATETIME DEFAULT '2026-05-13 18:00:00' NOT NULL"),
        ('updated_at', "DATETIME DEFAULT '2026-05-13 18:00:00' NOT NULL"),
        ('created_by', "VARCHAR"),
        ('updated_by', "VARCHAR"),
        ('is_deleted', "BOOLEAN DEFAULT 0 NOT NULL"),
        ('deleted_at', "DATETIME")
    ]
    
    for col, type in cols:
        try:
            cursor.execute(f"ALTER TABLE questions ADD COLUMN {col} {type}")
            print(f"Added column {col}")
        except Exception as e:
            print(f"Column {col} failed: {e}")
            
    conn.commit()
    conn.close()

if __name__ == '__main__':
    fix()
