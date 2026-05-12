import os
from sqlalchemy import create_engine, text, inspect

def governance_fix():
    print("Starting comprehensive educational governance database fix...")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set!")
        return

    engine = create_engine(db_url)
    with engine.connect() as conn:
        print("Connected successfully!")
        
        inspector = inspect(engine)
        
        def add_col(table, col, type_sql):
            columns = [c['name'] for c in inspector.get_columns(table)]
            if col not in columns:
                print(f"Adding {col} to {table}...")
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {type_sql};"))
                conn.commit()
            else:
                print(f"Column {col} already exists in {table}.")

        # Create Educational Reviews table
        tables = inspector.get_table_names()
        if "educational_reviews" not in tables:
            print("Creating educational_reviews table...")
            conn.execute(text("""
                CREATE TABLE educational_reviews (
                    id SERIAL PRIMARY KEY,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    reviewer_id INTEGER REFERENCES users(id) NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    comment TEXT,
                    override_payload JSONB,
                    confidence_level FLOAT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()
        
        # Create Educational Escalations table
        if "educational_escalations" not in tables:
            print("Creating educational_escalations table...")
            conn.execute(text("""
                CREATE TABLE educational_escalations (
                    id SERIAL PRIMARY KEY,
                    type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    severity TEXT NOT NULL DEFAULT 'MEDIUM',
                    trigger_payload JSONB,
                    resolution_payload JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()

        # Update learning_interventions
        add_col("learning_interventions", "risk_level", "TEXT DEFAULT 'LOW'")
        add_col("learning_interventions", "approval_status", "TEXT DEFAULT 'AUTO_APPROVED'")
        
        print("Educational governance schema fix complete!")

if __name__ == "__main__":
    governance_fix()
