from pydantic import BaseModel, EmailStr
from typing import Optional

class UserCreate(BaseModel):
    google_uid: str
    email: EmailStr
    full_name: Optional[str] = None
    profile_picture: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    google_uid: str
    email: EmailStr
    full_name: Optional[str]
    profile_picture: Optional[str]
    role: str

    class Config:
        from_attributes = True

class FirebaseTokenAuth(BaseModel):
    id_token: str
