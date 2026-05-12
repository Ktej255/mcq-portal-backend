from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import logging
import time
from contextlib import asynccontextmanager

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.firebase import init_firebase
from app.core.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize Limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting MCQ API...")
    init_firebase()
    yield
    # Shutdown
    logger.info("Shutting down MCQ API...")

app = FastAPI(title="MCQ Intelligence Portal API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from fastapi import HTTPException

# Specific handler for HTTPException to see what's being raised
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(f"FORENSIC | HTTP Error: {exc.status_code} | Detail: {exc.detail} | Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.detail, "data": None}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"FORENSIC | Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal Server Error", "data": None}
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS] if settings.BACKEND_CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware for request timing and security headers
@app.middleware("http")
async def add_process_time_and_security_headers(request: Request, call_next):
    start_time = time.time()
    
    # Debug logging for CORS and Auth
    origin = request.headers.get("origin")
    auth_header = request.headers.get("authorization")
    user_agent = request.headers.get("user-agent")
    
    logger.info(f"FORENSIC | Request Started | Method: {request.method} | Path: {request.url.path} | Origin: {origin} | Auth Present: {bool(auth_header)}")
    
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"FORENSIC | Request Exception during call_next: {str(e)}", exc_info=True)
        raise e

    process_time = time.time() - start_time
    
    logger.info(f"FORENSIC | Request Finished | Method: {request.method} | Path: {request.url.path} | Status: {response.status_code} | Duration: {process_time:.4f}s")
    
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

from app.api.v1 import auth, attempts, admin, dashboard, tests, reports

@app.get("/")
@limiter.limit("10/minute")
def read_root(request: Request):
    return {"success": True, "message": "Welcome to MCQ Intelligence Portal API", "data": None}

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/api/v1/test-public")
def test_public():
    return {"success": True, "message": "Public API route works", "data": None}

from app.schemas.common import StandardResponse
@app.get("/api/v1/test-empty-history")
def test_empty_history():
    return StandardResponse(success=True, message="History retrieved", data=[])

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(attempts.router, prefix="/api/v1/attempts", tags=["Attempts"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(tests.router, prefix="/api/v1/tests", tags=["Tests"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
