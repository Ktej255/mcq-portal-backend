from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.domain import User
from app.schemas.user import UserResponse
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse

router = APIRouter()

@router.get("/me", response_model=StandardResponse[UserResponse])
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """
    Returns the current user profile. If the user doesn't exist in the database yet, 
    the get_current_user dependency will automatically create it using the Firebase ID token.
    """
    return StandardResponse(success=True, message="User profile retrieved successfully", data=current_user)

