from fastapi import FastAPI

from app.api.v1.items import router as items_router


app = FastAPI(title="OmniSync", version="0.1.0")
app.include_router(items_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
