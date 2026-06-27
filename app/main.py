from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.gs_lms.gemini_discussion_provider import register_discussion_provider

# Wire up the real Gemini discussion provider (falls back to mock if no API key)
register_discussion_provider()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    # --- Startup ---
    # Register Cashfree payment service
    from app.core.payments.config import cashfree_config

    if cashfree_config.is_configured:
        try:
            from app.core.payments.service import CashfreePaymentService

            app.state.payment_service = CashfreePaymentService(cashfree_config)
            logger.info("Cashfree payment service initialized successfully")
        except Exception as e:
            logger.critical(
                "Failed to initialize Cashfree payment service: %s. "
                "Payment endpoints will return HTTP 503.",
                str(e),
            )
            app.state.payment_service = None
    else:
        logger.critical(
            "Cashfree credentials not configured. "
            "All payment endpoints will return HTTP 503."
        )
        app.state.payment_service = None

    yield

    # --- Shutdown ---
    # Clean up payment service if needed
    app.state.payment_service = None


app = FastAPI(
    title="MCQ Intelligence Portal",
    description="Institutional MCQ OS for high-stakes examinations.",
    version="2.0.0",
    lifespan=lifespan,
)

# Configure CORS
cors_origins = settings.BACKEND_CORS_ORIGINS
if isinstance(cors_origins, str):
    cors_origins = ["*"] if cors_origins == "*" else [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
from app.api.v1 import auth, admin, tests, reports, dashboard, revision, attempts, simulation, mains_upload
from app.api.v1 import optional
from app.api.v1 import gs_lms
from app.api.v1 import profile
from app.api.v1 import payments
from app.api.v1 import engagement

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(tests.router, prefix="/api/v1/tests", tags=["tests"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(revision.router, prefix="/api/v1/revision", tags=["revision"])
app.include_router(attempts.router, prefix="/api/v1/attempts", tags=["attempts"])
app.include_router(simulation.router, prefix="/api/v1/simulation", tags=["simulation"])
app.include_router(mains_upload.router, prefix="/api/v1/mains-upload", tags=["mains-upload"])
app.include_router(optional.router, prefix="/api/v1/optional", tags=["optional"])
app.include_router(gs_lms.router, prefix="/api/v1/gs-lms", tags=["gs-lms"])

# Dev preview route (no auth) for GS LMS content preview
from app.api.v1.gs_lms.preview import router as gs_lms_preview_router
app.include_router(gs_lms_preview_router, prefix="/api/v1/gs-lms", tags=["gs-lms-preview"])
app.include_router(profile.router, prefix="/api/v1/student", tags=["student-profile"])
app.include_router(payments.router, prefix="/api/v1/payments", tags=["payments"])
app.include_router(engagement.router, prefix="/api/v1/engagement", tags=["engagement"])


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
