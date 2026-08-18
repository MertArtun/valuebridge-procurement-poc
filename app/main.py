from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.approvals import ApprovalRequiredError
from app.mockdesk_client import HttpMockDeskGateway
from app.models import (
    ActionPreview,
    AnalysisResponse,
    ApprovalRecord,
    PurchaseRequest,
    TicketResult,
)
from app.service import ProcurementService
from app.store import SQLiteStore
from app.security import AuthorizationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _default_service() -> ProcurementService:
    store = SQLiteStore(Path(os.getenv("VALUEBRIDGE_DB_PATH", PROJECT_ROOT / "runtime/valuebridge.db")))
    gateway = HttpMockDeskGateway(os.getenv("MOCKDESK_URL", "http://mockdesk:8001"))
    return ProcurementService.from_project_data(
        store=store,
        mockdesk_gateway=gateway,
        project_root=PROJECT_ROOT,
    )


def create_app(service: ProcurementService | None = None) -> FastAPI:
    app = FastAPI(
        title="ValueBridge Procurement PoC",
        version="0.1.0",
        description="Forward-deployed procurement exception workflow case study.",
    )
    app.state.service = service or _default_service()
    templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))
    app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")), name="static")

    @app.exception_handler(AuthorizationError)
    async def authorization_error(_request: Request, exc: AuthorizationError):
        return _json_error(403, "FORBIDDEN", str(exc), retryable=False)

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
        return app.state.service.analyze(payload, role=x_demo_role, user=x_demo_user)

    @app.get("/api/v1/approvals/{approval_id}/action-preview", response_model=ActionPreview)
    def action_preview(
        approval_id: str,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> ActionPreview:
        del x_demo_user
        try:
            return app.state.service.action_preview(approval_id, role=x_demo_role)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/approvals/{approval_id}/approve", response_model=ApprovalRecord)
    def approve(
        approval_id: str,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> ApprovalRecord:
        try:
            return app.state.service.approve(approval_id, role=x_demo_role, user=x_demo_user)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/tool-actions/{approval_id}/execute", response_model=TicketResult)
    def execute(
        approval_id: str,
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ) -> TicketResult:
        try:
            return app.state.service.execute(approval_id, role=x_demo_role, user=x_demo_user)
        except ApprovalRequiredError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/audit/events")
    def audit_events(
        x_demo_role: str = Header(alias="X-Demo-Role"),
        x_demo_user: str = Header(alias="X-Demo-User"),
    ):
        del x_demo_user
        from app.security import authorize

        authorize(x_demo_role, "read_audit")
        return app.state.service.store.list_audit()

    return app


def _json_error(status_code: int, code: str, message: str, retryable: bool):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "trace_id": None,
                "retryable": retryable,
            }
        },
    )


app = create_app()
