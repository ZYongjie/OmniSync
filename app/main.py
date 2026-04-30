from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.v1.files import router as files_router
from app.api.v1.items import router as items_router


app = FastAPI(title="OmniSync", version="0.1.0")
app.include_router(items_router)
app.include_router(files_router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    static_page = Path(__file__).resolve().parent / "static" / "index.html"
    return FileResponse(static_page)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
