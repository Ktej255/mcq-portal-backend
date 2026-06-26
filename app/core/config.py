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

    # Clerk Auth Settings
    CLERK_JWT_KEY: Optional[str] = None
    CLERK_JWKS_URL: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    
    ADMIN_EMAILS: List[str] = ["sarit.kumar.dev@gmail.com"] # Add bootstrap admin
    SCHEMA_CHECK_STRICT: bool = False

    # Security: the `MOCK_TOKEN` auth bypass in `get_current_user` is a
    # dev/test/e2e affordance ONLY. It is gated behind this flag and defaults to
    # OFF so it can never be honored in production. Enable it explicitly (e.g.
    # `ALLOW_MOCK_AUTH=true` in an untracked local `.env` or a CI/e2e env) to run
    # Playwright/local flows that authenticate via `Bearer MOCK_TOKEN[_<uid>]`.
    # When off, a `MOCK_TOKEN` is treated as an invalid credential (401).
    ALLOW_MOCK_AUTH: bool = False

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()
