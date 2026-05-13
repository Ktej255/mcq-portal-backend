import os
import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    
    try:
        # Run alembic upgrade head
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Migration output:")
        logger.info(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error("Migration failed!")
        logger.error(e.stdout)
        logger.error(e.stderr)
        sys.exit(1)
    
    logger.info("Migrations completed successfully.")

if __name__ == "__main__":
    run_migrations()
