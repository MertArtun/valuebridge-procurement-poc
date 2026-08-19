from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.errors import ValueBridgeError
from app.llm import chat_client_from_env
from app.metrics import summarize
from app.mockdesk_client import HttpMockDeskGateway
from app.models import (
    ActionPreview,
    AnalysisResponse,
    ApprovalRecord,
    IntakeRequest,
    IntakeResponse,
    PolicyQaResponse,
    PolicyQuestion,
    PurchaseRequest,
    TicketResult,
)
from app.policy_qa import embedding_client_from_env
from app.rate_limit import TokenBucketLimiter
from app.security import authorize
from app.service import ProcurementService
from app.store import SQLiteStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# FastAPI's bundled docs UI loads its assets from a CDN plus one inline
# bootstrap script, which the strict CSP would block into a blank page.
_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}

_DEMO_RATE_LIMIT_CAPACITY = 30
_DEMO_RATE_LIMIT_PER_MINUTE = 30


def _default_service() -> ProcurementService:
    store = SQLiteStore(
        Path(os.getenv("VALUEBRIDGE_DB_PATH", PROJECT_ROOT / "runtime/valuebridge.db"))
    )
    gateway = HttpMockDeskGateway(os.getenv("MOCKDESK_URL", "http://mockdesk:8001"))
    return ProcurementService.from_project_data(
        store=store,
        mockdesk_gateway=gateway,
        project_root=PROJECT_ROOT,
        chat_client=chat_client_from_env(),
        embedding_client=embedding_client_from_env(),
    )


def create_app(
    service: ProcurementService | None = None,
    *,
    demo_mode: bool | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    if demo_mode is None:
        demo_mode = os.getenv("VALUEBRIDGE_DEMO_MODE") == "1"
    app = FastAPI(
        title="ValueBridge Procurement PoC",
        version="0.2.0",
        description="Forward-deployed procurement exception workflow case study.",
    )
    app.state.service = service
    templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))
    app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")), name="static")

    def resolve_service() -> ProcurementService:
        if app.state.service is None:
            app.state.service = _default_service()
        return app.state.service

    if demo_mode:
        limiter = TokenBucketLimiter(
            capacity=_DEMO_RATE_LIMIT_CAPACITY,
            refill_per_minute=_DEMO_RATE_LIMIT_PER_MINUTE,
            clock=clock,
        )

        # Registered before the header middleware so that it stays the inner
        # layer: a throttled response still carries the demo headers.
        @app.middleware("http")
        async def demo_rate_limit(request: Request, call_next):
            if not request.url.path.startswith("/api/"):
                return await call_next(request)
            retry_after = limiter.consume(_client_key(request))
            if retry_after is None:
                return await call_next(request)
            response = _json_error(
                429,
                "RATE_LIMITED",
                "Demo rate limit reached. Please retry shortly.",
                retryable=True,
            )
            response.headers["Retry-After"] = str(retry_after)
            return response

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path not in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
                "frame-ancestors 'none'"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if demo_mode:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.exception_handler(ValueBridgeError)
    async def valuebridge_error(_request: Request, exc: ValueBridgeError):
        return _json_error(
            exc.status_code,
            exc.code,
            str(exc),
            retryable=exc.retryable,
            trace_id=exc.trace_id,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "hero": {
                    "request_id": "PR-2026-0042",
                    "request_date": "2026-08-18",
                    "supplier_name": "Atlas Endüstri",
                    "category": "SPARE_PARTS",
                    "amount_try": "220000",
                    "received_quotes": 1,
                    "offered_lead_time_days": 20,
                }
            },
        )

    @app.post("/api/v1/requests/analyze", response_model=AnalysisResponse)
    def analyze_request(
        payload: PurchaseRequest,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> AnalysisResponse:
        return resolve_service().analyze(payload, role=x_demo_role, user=x_demo_user)

    @app.post("/api/v1/requests/intake", response_model=IntakeResponse)
    def intake_request(
        payload: IntakeRequest,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> IntakeResponse:
        return resolve_service().draft_intake(
            payload.text,
            role=x_demo_role,
            user=x_demo_user,
        )

    @app.post("/api/v1/policies/ask", response_model=PolicyQaResponse)
    def ask_policy_question(
        payload: PolicyQuestion,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> PolicyQaResponse:
        return resolve_service().ask_policy_question(
            payload.question,
            payload.on_date,
            role=x_demo_role,
            user=x_demo_user,
        )

    @app.get("/api/v1/approvals/{approval_id}/action-preview", response_model=ActionPreview)
    def action_preview(
        approval_id: str,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> ActionPreview:
        del x_demo_user
        try:
            return resolve_service().action_preview(approval_id, role=x_demo_role)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/approvals/{approval_id}/approve", response_model=ApprovalRecord)
    def approve(
        approval_id: str,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> ApprovalRecord:
        try:
            return resolve_service().approve(approval_id, role=x_demo_role, user=x_demo_user)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/approvals/{approval_id}/reject", response_model=ApprovalRecord)
    def reject(
        approval_id: str,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> ApprovalRecord:
        try:
            return resolve_service().reject(approval_id, role=x_demo_role, user=x_demo_user)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/tool-actions/{approval_id}/execute", response_model=TicketResult)
    def execute(
        approval_id: str,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> TicketResult:
        try:
            return resolve_service().execute(approval_id, role=x_demo_role, user=x_demo_user)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/audit/events")
    def audit_events(
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ):
        del x_demo_user
        authorize(x_demo_role, "read_audit")
        return resolve_service().store.list_audit()

    @app.get("/api/v1/metrics/summary")
    def metrics_summary(
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ):
        del x_demo_user
        authorize(x_demo_role, "read_audit")
        return summarize(resolve_service().store.list_audit())

    return app


def _client_key(request: Request) -> str:
    """Identify the caller behind the demo reverse proxy.

    The demo container publishes its port on loopback only, so every external
    call arrives through Caddy and the first X-Forwarded-For entry is the one
    Caddy appended for the real client.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


def _json_error(
    status_code: int,
    code: str,
    message: str,
    retryable: bool,
    trace_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "trace_id": trace_id,
                "retryable": retryable,
            }
        },
    )


app = create_app()
