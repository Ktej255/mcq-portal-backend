import os
from sqlalchemy import create_engine, text, inspect

def causal_fix():
    print("Starting comprehensive causal intelligence database fix...")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set!")
        return

    engine = create_engine(db_url)
    with engine.connect() as conn:
        print("Connected successfully!")
        
        inspector = inspect(engine)
        
        # Create Knowledge Concepts table
        tables = inspector.get_table_names()
        if "knowledge_concepts" not in tables:
            print("Creating knowledge_concepts table...")
            conn.execute(text("""
                CREATE TABLE knowledge_concepts (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    subject_id INTEGER REFERENCES subjects(id) NOT NULL,
                    description TEXT,
                    metadata_payload JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX idx_knowledge_concepts_name ON knowledge_concepts(name);
            """))
            conn.commit()
        
        # Create Knowledge Edges table
        if "knowledge_edges" not in tables:
            print("Creating knowledge_edges table...")
            conn.execute(text("""
                CREATE TABLE knowledge_edges (
                    id SERIAL PRIMARY KEY,
                    source_id INTEGER REFERENCES knowledge_concepts(id) NOT NULL,
                    target_id INTEGER REFERENCES knowledge_concepts(id) NOT NULL,
                    edge_type TEXT NOT NULL,
                    strength FLOAT DEFAULT 1.0,
                    evidence_quality FLOAT DEFAULT 1.0,
                    durability FLOAT DEFAULT 1.0,
                    metadata_payload JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX idx_knowledge_edges_type ON knowledge_edges(edge_type);
            """))
            conn.commit()

        # Create Causal Inferences table
        if "causal_inferences" not in tables:
            print("Creating causal_inferences table...")
            conn.execute(text("""
                CREATE TABLE causal_inferences (
                    id SERIAL PRIMARY KEY,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    estimate FLOAT NOT NULL,
                    confidence_interval JSONB,
                    p_value FLOAT,
                    evidence_support FLOAT,
                    confounders JSONB,
                    reasoning_payload JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX idx_causal_inferences_target ON causal_inferences(target_type, target_id);
            """))
            conn.commit()
        
        print("Causal intelligence schema fix complete!")

if __name__ == "__main__":
    causal_fix()
