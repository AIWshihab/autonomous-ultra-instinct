from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.ui.routes import router as ui_router

app = FastAPI(title="Autonomous Repair Agent", version="0.1.0")
app.include_router(api_router)
app.include_router(ui_router)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parents[1] / "static"), name="static")

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "autonomous-repair-agent"
}
