from fastapi import FastAPI

from app.api import auth

app = FastAPI(title="DeployLens API", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.include_router(auth.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
