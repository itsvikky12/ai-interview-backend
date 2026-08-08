from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.config import get_settings
from app.database import init_db
from app.utils.logger import setup_logging
from app.middleware.rate_limiter import RateLimitMiddleware
from app.api.v1 import auth, users, resumes, interviews, reports, admin, speech, recordings, coding, coding_admin, sql_assessment
from app.api.websocket import interview_ws, proctoring_ws, coding_ws

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(debug=settings.DEBUG)
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import PlainTextResponse


class CORSPreflightMiddleware:
    """
    Pure ASGI middleware that intercepts OPTIONS preflight requests and returns
    a permissive 200 OK response before CORSMiddleware or any other middleware
    can reject them. This fixes the '400 Bad Request' on preflight requests
    caused by origin mismatches in CORSMiddleware.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http" and scope.get("method") == "OPTIONS":
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, X-Requested-With",
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Max-Age": "600",
            }
            response = PlainTextResponse("OK", status_code=200, headers=headers)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


from app.middleware.security_headers import SecurityHeadersMiddleware

# --- Middleware stack (order matters: last added = first executed) ---
# 1. Security Headers
app.add_middleware(SecurityHeadersMiddleware)

# 2. CORSMiddleware handles CORS headers on normal (non-OPTIONS) requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Rate limiter
app.add_middleware(RateLimitMiddleware)

# 4. CORSPreflightMiddleware runs FIRST (added last), catches all OPTIONS
#    requests before they reach CORSMiddleware or RateLimitMiddleware
app.add_middleware(CORSPreflightMiddleware)

# REST routes
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(resumes.router, prefix="/api/v1")
app.include_router(interviews.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(speech.router, prefix="/api/v1")
app.include_router(recordings.router, prefix="/api/v1")
app.include_router(coding.router, prefix="/api/v1")
app.include_router(coding_admin.router, prefix="/api/v1")
app.include_router(sql_assessment.router, prefix="/api/v1")

# WebSocket routes
app.include_router(interview_ws.router)
app.include_router(proctoring_ws.router)
app.include_router(coding_ws.router)

# Serve local uploads in dev / fallback — matches StorageService's persistent media_dir
upload_dir = os.path.join(os.path.abspath(settings.MEDIA_ROOT), "uploads")
os.makedirs(upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")


@app.get("/health")
async def health():
    return {"status": "healthy", "version": settings.APP_VERSION}
