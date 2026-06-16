from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.core.firebase import init_firebase
from app.core.config import settings

# Initialize Firebase Admin
init_firebase()

app = FastAPI(
    title="MCQ Intelligence Portal",
    description="Institutional MCQ OS for high-stakes examinations.",
    version="2.0.0"
)

# Configure CORS
cors_origins = settings.BACKEND_CORS_ORIGINS
if isinstance(cors_origins, str):
    cors_origins = ["*"] if cors_origins == "*" else [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
from app.api.v1 import auth, admin, tests, reports, dashboard, revision, attempts, simulation, mains_upload, entitlements

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(tests.router, prefix="/api/v1/tests", tags=["tests"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(revision.router, prefix="/api/v1/revision", tags=["revision"])
app.include_router(attempts.router, prefix="/api/v1/attempts", tags=["attempts"])
app.include_router(simulation.router, prefix="/api/v1/simulation", tags=["simulation"])
app.include_router(mains_upload.router, prefix="/api/v1/mains-upload", tags=["mains-upload"])
app.include_router(entitlements.router, prefix="/api/v1/entitlements", tags=["entitlements"])


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "MCQ Intelligence Portal API",
        "timestamp": time.time(),
        "version": "2.0.0"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "clock": time.time()}
