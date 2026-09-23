import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.core.logging import configure_logging
from app.core.redis import redis_client
from app.websockets.pubsub import run_pubsub_listener
from app.modules.auth.router import router as auth_router
from app.modules.organizations.router import router as organizations_router
from app.modules.organizations.my_organization_router import (
    router as my_organization_router,
)
from app.modules.departments.router import router as departments_router
from app.modules.teams.router import router as teams_router
from app.modules.users.router import router as users_router
from app.modules.customers.router import public_router as customers_public_router
from app.modules.customers.router import router as customers_router
from app.modules.conversations.router import public_router as conversations_public_router
from app.modules.conversations.router import router as conversations_router
from app.modules.attachments.router import public_router as attachments_public_router
from app.modules.attachments.router import router as attachments_router
from app.modules.quick_replies.router import router as quick_replies_router
from app.modules.tickets.router import router as tickets_router
from app.modules.notifications.router import router as notifications_router
from app.modules.knowledge_base.router import public_router as kb_public_router
from app.modules.knowledge_base.router import router as kb_router
from app.modules.automation.router import router as automation_router
from app.modules.audit_logs.router import router as audit_logs_router
from app.modules.settings.router import router as settings_router
from app.modules.webhooks.router import router as webhooks_router
from app.modules.integration.router import router as integration_router

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The pub/sub listener is what makes WebSocket broadcasts work at all —
    # every real-time push (agent reply → customer widget, new message →
    # dashboard notification) flows through Redis and back via this task.
    listener_task = asyncio.create_task(run_pubsub_listener(redis_client))
    yield
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    description="API-first Customer Communication Platform",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Baseline headers every response should carry — none of these require
    any per-route code, so applying them once here beats trying to
    remember them on 19 modules' worth of routers.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

# ---------- Domain exception → HTTP response mapping ----------
_STATUS_MAP = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    UnauthorizedError: status.HTTP_401_UNAUTHORIZED,
    ForbiddenError: status.HTTP_403_FORBIDDEN,
    ConflictError: status.HTTP_409_CONFLICT,
    ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status_code = _STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
    return JSONResponse(status_code=status_code, content={"detail": exc.message})


# ---------- Routers ----------
# Each module registers its router here as it's built, per the module
# roadmap in docs/architecture — this file grows by one line per module,
# never by adding logic.
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(my_organization_router)
app.include_router(departments_router)
app.include_router(teams_router)
app.include_router(users_router)
app.include_router(customers_public_router)
app.include_router(customers_router)
app.include_router(conversations_public_router)
app.include_router(conversations_router)
app.include_router(attachments_public_router)
app.include_router(attachments_router)
app.include_router(quick_replies_router)
app.include_router(tickets_router)
app.include_router(notifications_router)
app.include_router(kb_public_router)
app.include_router(kb_router)
app.include_router(automation_router)
app.include_router(audit_logs_router)
app.include_router(settings_router)
app.include_router(webhooks_router)
# API-key authenticated surface for external systems (CRM/ERP/bots).
app.include_router(integration_router)


@app.get("/api/health", tags=["Health"])
async def health_check() -> dict:
    return {"status": "ok", "service": settings.APP_NAME}
