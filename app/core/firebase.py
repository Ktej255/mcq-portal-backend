import os
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)

from app.core.config import settings

def init_firebase():
    if not firebase_admin._apps:
        try:
            # Determine project ID for logging
            project_id = settings.FIREBASE_PROJECT_ID or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("FIREBASE_PROJECT_ID")
            logger.info(f"Initializing Firebase Admin for project: {project_id}")
            
            # Use specific credentials if available, otherwise default ADC
            if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
                cred = credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()
            logger.info("Firebase Admin initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin: {e}")

def verify_token(id_token: str) -> dict:
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        logger.error(f"Firebase token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
