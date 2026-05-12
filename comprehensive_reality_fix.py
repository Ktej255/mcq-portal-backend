import os
from sqlalchemy import create_engine, text, inspect

def reality_fix():
    print("Starting comprehensive reality grounding database fix...")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set!")
        return

    engine = create_engine(db_url)
    with engine.connect() as conn:
        print("Connected successfully!")
        
        inspector = inspect(engine)
        
        # Create Qualitative Signals table
        tables = inspector.get_table_names()
        if "qualitative_signals" not in tables:
            print("Creating qualitative_signals table...")
            conn.execute(text("""
                CREATE TABLE qualitative_signals (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) NOT NULL,
                    signal_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    evidence_payload JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX idx_qualitative_signals_type ON qualitative_signals(signal_type);
            """))
            conn.commit()
        
        # Create Reality Audits table
        if "reality_audits" not in tables:
            print("Creating reality_audits table...")
            conn.execute(text("""
                CREATE TABLE reality_audits (
                    id SERIAL PRIMARY KEY,
                    auditor_id INTEGER REFERENCES users(id) NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    divergence_score FLOAT NOT NULL,
                    findings TEXT,
                    reconciliation_payload JSONB,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX idx_reality_audits_target ON reality_audits(target_type, target_id);
            """))
            conn.commit()

        # Create Cultural Contexts table
        if "cultural_contexts" not in tables:
            print("Creating cultural_contexts table...")
            conn.execute(text("""
                CREATE TABLE cultural_contexts (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    governance_rules JSONB,
                    pedagogical_patterns JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX idx_cultural_contexts_name ON cultural_contexts(name);
            """))
            conn.commit()
        
        print("Reality grounding schema fix complete!")

if __name__ == "__main__":
    reality_fix()
