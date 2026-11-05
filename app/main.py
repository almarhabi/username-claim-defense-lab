from __future__ import annotations

import hmac
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, load_settings
from .database import Database
from .service import LabError, LabService


class LoginRequest(BaseModel):
    username: str
    password: str


class RaceRequest(BaseModel):
    name: str = "rare"
    contenders: int = Field(default=8, ge=2, le=16)


class BurstRequest(BaseModel):
    account: str = "alice"
    requests: int = Field(default=50, ge=1, le=500)
    name: str = "burst"


class TransferRequest(BaseModel):
    name: str
    source: str
    target: str


class UserTransferRequest(BaseModel):
    target_account: str


class DefenseRequest(BaseModel):
    enabled: bool


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    database = Database(settings.database_path)
    service = LabService(database, settings)
    app = FastAPI(
        title="Username Claim Defense Lab",
        version="1.0.0",
        description="A self-contained synthetic platform. It contains no real social-network integration.",
    )
    app.state.service = service
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.exception_handler(LabError)
    async def lab_error_handler(_: Request, exc: LabError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    def require_admin(x_lab_key: Annotated[str, Header(alias="X-Lab-Key")] = "") -> None:
        if not hmac.compare_digest(x_lab_key, settings.admin_key):
            raise HTTPException(status_code=403, detail="Invalid lab administration key")

    def current_account(authorization: Annotated[str, Header()] = "") -> str:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Use a synthetic Bearer lab session")
        account = service.authenticate(token)
        if account is None:
            raise HTTPException(status_code=401, detail="Invalid or expired lab session")
        return account

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "lab_only": True, "domain": "social.lab.internal"}

    @app.post("/v1/auth/sessions", status_code=status.HTTP_201_CREATED)
    def login(body: LoginRequest) -> dict[str, Any]:
        session = service.create_session(body.username, body.password)
        if session is None:
            raise HTTPException(status_code=401, detail="Invalid synthetic account credentials")
        return session

    @app.delete("/v1/auth/sessions", status_code=status.HTTP_204_NO_CONTENT)
    def logout(authorization: Annotated[str, Header()] = "") -> None:
        _, _, token = authorization.partition(" ")
        service.revoke_session(token)

    @app.get("/v1/accounts")
    def accounts() -> list[dict[str, Any]]:
        return service.list_accounts()

    @app.get("/v1/usernames")
    def usernames() -> list[dict[str, Any]]:
        return service.list_usernames()

    @app.post("/v1/usernames/{name}/claim")
    def claim(name: str, account: Annotated[str, Depends(current_account)]) -> JSONResponse:
        result = service.claim(name, account)
        response_status = {"claimed": 200, "taken": 409, "cooldown": 409, "rate_limited": 429}.get(
            result["status"], 200
        )
        return JSONResponse(status_code=response_status, content=result)

    @app.post("/v1/usernames/{name}/release")
    def release(name: str, account: Annotated[str, Depends(current_account)]) -> dict[str, Any]:
        return service.release(name, account)

    @app.post("/v1/usernames/{name}/transfer")
    def transfer(
        name: str, body: UserTransferRequest, account: Annotated[str, Depends(current_account)]
    ) -> dict[str, Any]:
        return service.transfer(name, account, body.target_account)

    @app.post("/v1/lab/reset", dependencies=[Depends(require_admin)])
    def reset() -> dict[str, str]:
        service.db.reset()
        return {"status": "reset", "fixture_password": "lab-only-password"}

    @app.post("/v1/lab/defenses", dependencies=[Depends(require_admin)])
    def defenses(body: DefenseRequest) -> dict[str, Any]:
        return service.set_defenses(body.enabled)

    @app.post("/v1/lab/race", dependencies=[Depends(require_admin)])
    def race(body: RaceRequest) -> dict[str, Any]:
        return service.simulate_race(body.name, body.contenders)

    @app.post("/v1/lab/burst", dependencies=[Depends(require_admin)])
    def burst(body: BurstRequest) -> dict[str, Any]:
        return service.simulate_burst(body.account, body.requests, body.name)

    @app.post("/v1/lab/transfer", dependencies=[Depends(require_admin)])
    def lab_transfer(body: TransferRequest) -> dict[str, Any]:
        return service.transfer(body.name, body.source, body.target)

    @app.get("/v1/lab/audit", dependencies=[Depends(require_admin)])
    def audit(limit: int = 100) -> list[dict[str, Any]]:
        return service.audit_events(limit)

    @app.get("/v1/lab/metrics")
    def metrics() -> dict[str, Any]:
        return service.metrics()

    return app


app = create_app()
