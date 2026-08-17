from fastapi import FastAPI

from app.api import auth, deployments, repositories, webhooks
from app.api.errors import install_github_error_handlers

app = FastAPI(title="DeployLens API", docs_url="/api/docs", openapi_url="/api/openapi.json")

install_github_error_handlers(app)
app.include_router(auth.router)
app.include_router(repositories.router)
app.include_router(deployments.router)
app.include_router(webhooks.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
