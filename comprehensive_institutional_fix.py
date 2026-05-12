import os
from sqlalchemy import create_engine, text, inspect

def institutional_fix():
    print("Starting comprehensive institutional database fix...")
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

        # Create Institutions table
        tables = inspector.get_table_names()
        if "institutions" not in tables:
            print("Creating institutions table...")
            conn.execute(text("""
                CREATE TABLE institutions (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    config JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()
        
        # Create Cohorts table
        if "cohorts" not in tables:
            print("Creating cohorts table...")
            conn.execute(text("""
                CREATE TABLE cohorts (
                    id SERIAL PRIMARY KEY,
                    institution_id INTEGER REFERENCES institutions(id) NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()

        # Create Cohort Memberships table
        if "cohort_memberships" not in tables:
            print("Creating cohort_memberships table...")
            conn.execute(text("""
                CREATE TABLE cohort_memberships (
                    id SERIAL PRIMARY KEY,
                    cohort_id INTEGER REFERENCES cohorts(id) NOT NULL,
                    user_id INTEGER REFERENCES users(id) NOT NULL,
                    role TEXT NOT NULL DEFAULT 'STUDENT',
                    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()

        # Add institution_id to users
        add_col("users", "institution_id", "INTEGER REFERENCES institutions(id)")
        
        print("Institutional schema fix complete!")

if __name__ == "__main__":
    institutional_fix()
