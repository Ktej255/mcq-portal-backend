import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug():
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info("Listing files in current directory:")
    logger.info(os.listdir("."))
    
    if os.path.exists("alembic"):
        logger.info("Listing files in alembic/versions:")
        logger.info(os.listdir("alembic/versions"))
    else:
        logger.error("alembic directory not found!")
    
    try:
        logger.info("Running: alembic current")
        res = subprocess.run(["alembic", "current"], capture_output=True, text=True)
        logger.info(f"STDOUT: {res.stdout}")
        logger.info(f"STDERR: {res.stderr}")
    except Exception as e:
        logger.error(f"Error running alembic: {e}")

if __name__ == "__main__":
    debug()
