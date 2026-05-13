import os
import sys
import subprocess
import logging

import sqlalchemy as sa
from sqlalchemy import inspect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_schema(db_url):
    try:
        print(f"DEBUG: Checking current database schema...")
        engine = sa.create_engine(db_url)
        inspector = inspect(engine)
        columns = [c['name'] for c in inspector.get_columns('reports')]
        print(f"DEBUG: Columns in 'reports' table: {columns}")
        return columns
    except Exception as e:
        print(f"DEBUG: Error checking schema: {e}")
        return []

def run_migrations():
    logger.info("Starting database migrations...")
    
    # Ensure we are in the backend directory
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(backend_dir)
    
    # Check for DATABASE_URL
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL environment variable not set!")
        sys.exit(1)
    
    logger.info(f"Using database URL: {db_url[:20]}...")
    
    # Check actual schema first
    check_schema(db_url)
    
    try:
        # Check current version
        print("DEBUG: Checking current migration version...")
        subprocess.run(["alembic", "current"], check=False)
        
        # Run alembic upgrade head
        print("DEBUG: Running alembic upgrade head...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Migration STDOUT:")
        logger.info(result.stdout)
        logger.info("Migration STDERR:")
        logger.info(result.stderr)
    except subprocess.CalledProcessError as e:
        logger.error("Migration failed!")
        logger.error(e.stdout)
        logger.error(e.stderr)
        sys.exit(1)
    
    logger.info("Migrations completed successfully.")

if __name__ == "__main__":
    run_migrations()
