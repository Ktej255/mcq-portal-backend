from pydantic_settings import BaseSettings
from pydantic import validator, AnyHttpUrl
from typing import Optional, List, Union

class Settings(BaseSettings):
    PROJECT_NAME: str = "MCQ Intelligence Portal"
    
    # DB Configuration
    DATABASE_URL: Optional[str] = "postgresql://postgres:password@localhost:5432/mcq_portal"

    @validator("DATABASE_URL", pre=True)
    def assemble_db_url(cls, v: Optional[str]) -> str:
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    # CORS Configuration
    BACKEND_CORS_ORIGINS: List[Union[AnyHttpUrl, str]] = ["http://localhost:3000", "http://localhost:8000"]

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # GCP / Firebase
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    FIREBASE_PROJECT_ID: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
