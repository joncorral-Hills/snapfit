"""SnapFit FastAPI application — tool holder configurator backend."""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Optional

from pydantic import BaseModel

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from database import engine, get_db
from models import Base, Tool, ToolSubmission
from seed import seed
from stl_generator import OUTPUT_DIR, MountingSystem, generate_holder
from image_analyzer import analyze_tool_image, extract_polygon_points

logger = logging.getLogger(__name__)

# ── App bootstrap ─────────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)
seed()

app = FastAPI(title="SnapFit", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_hex(32))
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "snapfit-admin")
_signer = URLSafeTimedSerializer(SECRET_KEY)
_SESSION_COOKIE = "snapfit_admin_session"

# ── Auth helpers ──────────────────────────────────────────────────────────────

def _make_session_token() -> str:
    return _signer.dumps("admin")


def _verify_session(request: Request) -> bool:
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return False
    try:
        _signer.loads(token, max_age=3600 * 8)  # 8-hour session
        return True
    except (BadSignature, SignatureExpired):
        return False


# ── Public routes ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/brands")
async def list_brands(db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    """Return sorted list of distinct brands."""
    brands = sorted({row.brand for row in db.query(Tool.brand).distinct()})
    return JSONResponse(content={"brands": brands})


@app.get("/api/tools")
async def list_tools(
    db: Annotated[Session, Depends(get_db)],
    brand: Optional[str] = None,
    search: Optional[str] = None,
) -> JSONResponse:
    """Return tools, optionally filtered by brand and/or a free-text search."""
    q = db.query(Tool)
    if brand:
        q = q.filter(Tool.brand == brand)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            Tool.brand.ilike(pattern)
            | Tool.model_name.ilike(pattern)
            | Tool.tool_type.ilike(pattern)
        )
    tools = [t.to_dict() for t in q.order_by(Tool.brand, Tool.model_name).all()]
    return JSONResponse(content={"tools": tools})


@app.get("/api/tools/{tool_id}")
async def get_tool(
    tool_id: int, db: Annotated[Session, Depends(get_db)]
) -> JSONResponse:
    tool = db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return JSONResponse(content=tool.to_dict())


class GenerateRequest(BaseModel):
    mounting_system: MountingSystem = "magnetic"


@app.post("/api/generate/{tool_id}")
async def generate_stl(
    tool_id: int,
    body: GenerateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    """Generate holder STL for tool_id with the selected mounting_system."""
    tool = db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    stl_path = generate_holder(tool, body.mounting_system)
    return JSONResponse(content={"filename": stl_path.name})


class GenerateFromDimsRequest(BaseModel):
    """Request body for scanned/custom tools that have no DB entry."""
    width_mm:         float
    height_mm:        float
    depth_mm:         float = 80.0
    mounting_system:  MountingSystem = "magnetic"
    label:            str = "custom"


@app.post("/api/generate-from-dims")
async def generate_from_dims(body: GenerateFromDimsRequest) -> JSONResponse:
    """Generate a holder STL from raw dimensions (no DB lookup required).

    Used by the camera scanner flow where the tool has been measured but
    hasn't been saved to the database.
    """
    tool = SimpleNamespace(
        body_width_mm=body.width_mm,
        body_height_mm=body.height_mm,
        body_depth_mm=body.depth_mm,
        model_name=body.label,
        brand="Scanned",
    )
    try:
        stl_path = generate_holder(tool, body.mounting_system)
    except Exception as exc:
        logger.exception("generate_from_dims failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(content={"filename": stl_path.name})


@app.get("/api/download/{filename}")
async def download_stl(filename: str) -> FileResponse:
    """Stream an already-generated STL file to the client."""
    # Prevent path traversal
    safe_name = Path(filename).name
    stl_path = OUTPUT_DIR / safe_name
    if not stl_path.exists():
        raise HTTPException(status_code=404, detail="STL not found — generate first")
    return FileResponse(
        path=str(stl_path),
        media_type="application/octet-stream",
        filename=safe_name,
    )

# ── Image analysis ────────────────────────────────────────────────────────────

class ToolImageRequest(BaseModel):
    """Request body for POST /api/analyze-tool-image."""
    image: str                        # base64-encoded JPEG or PNG (data-URL prefix ok)
    known_dimension_mm: float = 200.0 # one real-world measurement for px→mm calibration
    known_axis: str = "height"        # which axis the known dim applies to


@app.post("/api/analyze-tool-image")
async def analyze_tool_image_endpoint(body: ToolImageRequest) -> JSONResponse:
    """Analyse a base64-encoded tool photo, return bounding-box dimensions in mm.

    Pass `known_dimension_mm` + `known_axis` to calibrate pixel → mm conversion.
    A `confidence` score < 0.6 means the silhouette was unclear — retake the photo.
    `depth_mm` is always null (can't be inferred from a single 2D image).
    """
    try:
        result = analyze_tool_image(
            b64_image=body.image,
            known_dimension_mm=body.known_dimension_mm,
            known_axis=body.known_axis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in analyze_tool_image")
        raise HTTPException(status_code=500, detail="Image analysis failed.") from exc
    return JSONResponse(content=result)


class ContourRequest(BaseModel):
    """Request body for POST /api/analyze-contour."""
    image: str           # base64-encoded JPEG/PNG
    target_pts: int = 12 # target number of polygon control points (4-16)


@app.post("/api/analyze-contour")
async def analyze_contour_endpoint(body: ContourRequest) -> JSONResponse:
    """Return a simplified polygon outline (8-16 XY points in 0-1 fraction space).

    Used by the Step 2 SVG dot editor to display draggable control points
    over the frozen camera frame.
    """
    try:
        result = extract_polygon_points(
            b64_image=body.image,
            target_pts=max(4, min(body.target_pts, 16)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in analyze_contour")
        raise HTTPException(status_code=500, detail="Contour analysis failed.") from exc
    return JSONResponse(content=result)


async def submit_tool(
    brand: Annotated[str, Form()],
    model_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    """Stub: record a user tool-submission request for later review."""
    submission = ToolSubmission(brand=brand, model_name=model_name, email=email)
    db.add(submission)
    db.commit()
    return JSONResponse(content={"status": "received", "message": "Thanks! We'll review your submission."})


# ── Admin routes ──────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    if not _verify_session(request):
        return templates.TemplateResponse(
            "admin.html", {"request": request, "authenticated": False}
        )
    tools = SessionLocal_for_admin()
    return templates.TemplateResponse(
        "admin.html", {"request": request, "authenticated": True, "tools": tools}
    )


def SessionLocal_for_admin() -> list[dict]:
    """Fetch all tools for the admin view (avoids dependency injection in non-async context)."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        return [t.to_dict() for t in db.query(Tool).order_by(Tool.brand, Tool.model_name).all()]
    finally:
        db.close()


@app.post("/admin/login")
async def admin_login(
    request: Request,
    password: Annotated[str, Form()],
) -> RedirectResponse:
    if password != ADMIN_PASSWORD:
        response = templates.TemplateResponse(
            "admin.html",
            {"request": request, "authenticated": False, "error": "Incorrect password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        return response  # type: ignore[return-value]
    token = _make_session_token()
    redirect = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(key=_SESSION_COOKIE, value=token, httponly=True, samesite="lax")
    return redirect


@app.post("/admin/tools")
async def admin_add_tool(
    request: Request,
    brand: Annotated[str, Form()],
    model_name: Annotated[str, Form()],
    tool_type: Annotated[str, Form()],
    body_width_mm: Annotated[float, Form()],
    body_depth_mm: Annotated[float, Form()],
    body_height_mm: Annotated[float, Form()],
    handle_diameter_mm: Annotated[float, Form()],
    weight_kg: Annotated[float, Form()],
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    if not _verify_session(request):
        raise HTTPException(status_code=403, detail="Forbidden")
    tool = Tool(
        brand=brand, model_name=model_name, tool_type=tool_type,
        body_width_mm=body_width_mm, body_depth_mm=body_depth_mm,
        body_height_mm=body_height_mm, handle_diameter_mm=handle_diameter_mm,
        weight_kg=weight_kg,
    )
    db.add(tool)
    db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
