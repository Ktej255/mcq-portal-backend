from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional, List, Union, Any, ClassVar

class Settings(BaseSettings):
    PROJECT_NAME: str = "MCQ Intelligence Portal"
    
    # DB Configuration
    DATABASE_URL: Optional[str] = "postgresql://postgres:password@localhost:5432/mcq_portal"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if isinstance(v, str):
            # Strip literal quotes that sometimes get injected by shell/GCP
            v = v.strip("'").strip('"')
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql://", 1)
        return v

    # CORS Configuration
    DEFAULT_CORS_ORIGINS: ClassVar[List[str]] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://mcq-portal-frontend-yo5i.vercel.app",
        "https://mcq-portal-frontend.vercel.app",
    ]
    BACKEND_CORS_ORIGINS: Any = DEFAULT_CORS_ORIGINS.copy()

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
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
    SCHEMA_CHECK_STRICT: bool = False

    # Cashfree Payments (PG). Leave unset to keep payment endpoints disabled (503).
    CASHFREE_APP_ID: Optional[str] = None
    CASHFREE_SECRET_KEY: Optional[str] = None
    CASHFREE_ENV: str = "sandbox"  # "sandbox" | "production"
    # Public URLs used for redirect + webhook
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    BACKEND_BASE_URL: Optional[str] = None  # e.g. https://api.upsccommand.com

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()
