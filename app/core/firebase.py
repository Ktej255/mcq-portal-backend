import os
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)

def init_firebase():
    if not firebase_admin._apps:
        try:
            # Expected to be loaded via environment variables in production (e.g., GOOGLE_APPLICATION_CREDENTIALS)
            # For local dev, we could pass a cert dict or just let it auto-discover if creds are set.
            # Here we let it discover from GOOGLE_APPLICATION_CREDENTIALS or default ADC.
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialized successfully via Application Default Credentials.")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin: {e}")
            # If ADC fails, try to initialize without specific creds (useful in some GCP environments)
            try:
                firebase_admin.initialize_app()
                logger.info("Firebase Admin initialized successfully without explicit credentials.")
            except Exception as inner_e:
                logger.error(f"Failed fallback initialization for Firebase Admin: {inner_e}")

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
