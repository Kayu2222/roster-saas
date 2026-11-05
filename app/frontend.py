"""Serves the built React app (frontend/dist, or /app/web inside Docker) from the same origin as the API.

Same origin means no CORS setup and one URL for the whole product. Any path that isn't
an API route or a real file gets index.html, so the React router can handle it.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_ROOT = Path(__file__).resolve().parent.parent
_RESERVED = ("api/", "docs", "redoc", "openapi.json", "health")


def find_web_dir() -> Path | None:
    for candidate in (_ROOT / "web", _ROOT / "frontend" / "dist"):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def register_frontend(app: FastAPI, web_dir: Path | None) -> None:
    """Call last, after all API routers, so API routes always win."""
    if web_dir is None:
        return  # API-only (local dev with Vite, or tests)
    web_dir = web_dir.resolve()

    assets = web_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(_RESERVED):
            raise HTTPException(404, "Not found")
        candidate = (web_dir / path).resolve()
        # Serve real files (favicon etc.), never anything outside web_dir.
        if path and candidate.is_file() and candidate.is_relative_to(web_dir):
            return FileResponse(candidate)
        return FileResponse(web_dir / "index.html")
