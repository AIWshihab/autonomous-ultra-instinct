from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter()
dashboard_path = Path(__file__).resolve().parents[2] / "templates" / "dashboard.html"


@router.get("/dashboard", include_in_schema=False)
async def dashboard():
    return FileResponse(dashboard_path)


@router.get("/ui", include_in_schema=False)
async def ui():
    return FileResponse(dashboard_path)
