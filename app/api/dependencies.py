from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.domain import User, RoleEnum
from app.core.firebase import verify_token
from app.core.config import settings

from typing import Optional

security = HTTPBearer(auto_error=False)

import logging
logger = logging.getLogger(__name__)

def get_current_user(db: Session = Depends(get_db), auth: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> User:
    auth_provided = bool(auth)
    logger.info(f"FORENSIC | get_current_user check | Auth provided: {auth_provided}")
    
    if not auth:
        logger.warning("FORENSIC | No auth credentials provided in request headers")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated: No Bearer token found in headers",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials: Token verification failed",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token_cred = auth.credentials.strip() if auth.credentials else ""
        logger.info(f"FORENSIC | Received credentials: '{token_cred}'")
        if token_cred.startswith("MOCK_TOKEN"):
            logger.warning(f"FORENSIC | Using MOCK_TOKEN bypass: {token_cred}")
            
            # Support MOCK_TOKEN_<google_uid> for persona simulation
            if "_" in token_cred:
                target_uid = token_cred.split("_", 1)[1]
                user = db.query(User).filter(User.google_uid == target_uid).first()
                if user:
                    return user
            
            # Default fallback for legacy MOCK_TOKEN
            user = db.query(User).filter(User.google_uid == "dev-validator-id").first()
            if not user:
                user = User(
                    google_uid="dev-validator-id",
                    email="validator@antigravity.os",
                    full_name="Institutional Validator",
                    role=RoleEnum.ADMIN
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            return user
        decoded_token = verify_token(auth.credentials)
    except Exception as e:
        logger.error(f"FORENSIC | Token verification exception: {str(e)}")
        raise credentials_exception

    google_uid = decoded_token.get("uid")
    email = decoded_token.get("email")
    name = decoded_token.get("name")
    picture = decoded_token.get("picture")
    
    logger.info(f"FORENSIC | Token Decoded | UID: {google_uid} | Email: {email}")

    if not google_uid or not email:
        logger.error("FORENSIC | Token missing UID or Email claims")
        raise credentials_exception

    user = db.query(User).filter(User.google_uid == google_uid).first()
    
    # Check if user should be an admin based on email
    is_bootstrap_admin = email in settings.ADMIN_EMAILS
    
    # Auto-create user on first login
    if not user:
        logger.info(f"FORENSIC | User not found in DB, auto-creating account for {email}")
        user = User(
            google_uid=google_uid,
            email=email,
            full_name=name,
            profile_picture=picture,
            role=RoleEnum.ADMIN if is_bootstrap_admin else RoleEnum.STUDENT
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif is_bootstrap_admin and user.role != RoleEnum.ADMIN:
        logger.info(f"FORENSIC | Elevating user {email} to ADMIN based on allowlist")
        user.role = RoleEnum.ADMIN
        db.commit()
        db.refresh(user)
    else:
        logger.info(f"FORENSIC | User found in DB | Role: {user.role}")
        
    return user

def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    logger.info(f"FORENSIC | get_current_admin check | User: {current_user.email} | Role: {current_user.role}")
    if current_user.role != "ADMIN" and current_user.role != RoleEnum.ADMIN:
        logger.warning(f"FORENSIC | ACCESS DENIED | User {current_user.email} attempted admin access with role {current_user.role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Admin privileges required. Your current role is {current_user.role}"
        )
    return current_user
