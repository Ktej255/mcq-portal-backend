from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.domain import User, RoleEnum
from app.core.firebase import verify_token

security = HTTPBearer()

def get_current_user(db: Session = Depends(get_db), auth: HTTPAuthorizationCredentials = Depends(security)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    decoded_token = verify_token(auth.credentials)
    google_uid = decoded_token.get("uid")
    email = decoded_token.get("email")
    name = decoded_token.get("name")
    picture = decoded_token.get("picture")
    
    if not google_uid or not email:
        raise credentials_exception

    user = db.query(User).filter(User.google_uid == google_uid).first()
    
    # Auto-create user on first login
    if not user:
        user = User(
            google_uid=google_uid,
            email=email,
            full_name=name,
            profile_picture=picture,
            role=RoleEnum.STUDENT
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
    return user

def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user
