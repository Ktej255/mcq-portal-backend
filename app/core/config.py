from pydantic_settings import BaseSettings
from pydantic import validator, AnyHttpUrl
from typing import Optional, List, Union, Any, ClassVar

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
    DEFAULT_CORS_ORIGINS: ClassVar[List[str]] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "https://mcq-portal-frontend-yo5i.vercel.app",
        "https://mcq-portal-frontend.vercel.app",
    ]
    BACKEND_CORS_ORIGINS: Any = DEFAULT_CORS_ORIGINS.copy()

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[str, List[str]]:
        if isinstance(v, str):
            if v.strip() == "*":
                return "*"
            if v.startswith("[") and v.endswith("]"):
                try:
                    import json
                    parsed = json.loads(v)
                    values = parsed if isinstance(parsed, list) else [parsed]
                    return list(dict.fromkeys([*cls.DEFAULT_CORS_ORIGINS, *[str(i).strip() for i in values if str(i).strip()]]))
                except:
                    pass
            values = [i.strip() for i in v.split(",") if i.strip()]
            return list(dict.fromkeys([*cls.DEFAULT_CORS_ORIGINS, *values]))
        if isinstance(v, list):
            return list(dict.fromkeys([*cls.DEFAULT_CORS_ORIGINS, *v]))
        return cls.DEFAULT_CORS_ORIGINS.copy()

    # GCP / Firebase
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    FIREBASE_PROJECT_ID: Optional[str] = "mcq-intelligence-portal"
    GOOGLE_API_KEY: Optional[str] = None
    
    ADMIN_EMAILS: List[str] = ["sarit.kumar.dev@gmail.com"] # Add bootstrap admin

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
