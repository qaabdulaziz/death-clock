"""FastAPI application and JSON API."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.models import ProjectInput, SettingsUpdate
from app.projection import add_months, calculate_projection

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
LOCAL_AUTHORITY = re.compile(
    r"(?:(localhost|127\.0\.0\.1|testserver)|(\[::1\]))(?::([0-9]{1,5}))?",
    re.IGNORECASE,
)


def normalize_local_authority(value: str) -> str | None:
    """Return a canonical loopback authority, rejecting malformed Host values."""

    match = LOCAL_AUTHORITY.fullmatch(value.strip())
    if not match:
        return None
    port = int(match.group(3)) if match.group(3) else None
    if port is not None and not 1 <= port <= 65535:
        return None
    host = match.group(1).lower() if match.group(1) else "[::1]"
    return f"{host}:{port}" if port is not None else host


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    yield
    db.reset_connection()


app = FastAPI(title="Death Clock", lifespan=lifespan)


@app.middleware("http")
async def local_security(request: Request, call_next):
    """Reject cross-origin writes and keep private API responses out of caches."""

    authority = normalize_local_authority(request.headers.get("host", ""))
    if authority is None:
        return JSONResponse(status_code=400, content={"detail": "Invalid host header"})
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        origin = request.headers.get("origin")
        expected_origin = f"{request.url.scheme}://{authority}"
        if origin and origin.lower() != expected_origin.lower():
            return JSONResponse(status_code=403, content={"detail": "Cross-origin writes are not allowed"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return db.get_settings()


@app.put("/api/settings")
def put_settings(payload: SettingsUpdate) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    updates = {
        key: value
        for key, value in values.items()
        if value is not None or key == "date_of_birth"
    }
    if updates.get("date_of_birth", object()) is None:
        updates["setup_complete"] = False
    proposed = {**db.get_settings(), **updates}
    if proposed["setup_complete"] and not proposed["date_of_birth"]:
        raise HTTPException(
            status_code=422,
            detail="A date of birth is required to complete setup",
        )
    if proposed["date_of_birth"]:
        try:
            birth_date = date.fromisoformat(str(proposed["date_of_birth"]))
            add_months(birth_date, round(float(proposed["life_expectancy_years"]) * 12))
        except (OverflowError, ValueError):
            raise HTTPException(
                status_code=422,
                detail="The birth date and life expectancy exceed the supported calendar range",
            ) from None
    return db.update_settings(updates)


@app.get("/api/projects")
def get_projects() -> list[dict[str, Any]]:
    return db.list_projects()


@app.post("/api/projects", status_code=status.HTTP_201_CREATED)
def post_project(payload: ProjectInput) -> dict[str, Any]:
    return db.create_project(payload.name, payload.cost)


@app.put("/api/projects/{project_id}")
def put_project(project_id: int, payload: ProjectInput) -> dict[str, Any]:
    project = db.update_project(project_id, payload.name, payload.cost)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int) -> Response:
    if not db.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/projection")
def get_projection() -> dict[str, Any]:
    settings = db.get_settings()
    if not settings["date_of_birth"]:
        raise HTTPException(status_code=409, detail="Complete setup before requesting a projection")
    return calculate_projection(settings, db.list_projects())


@app.post("/api/reset")
def reset() -> dict[str, Any]:
    return db.reset_all()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
