from fastapi import FastAPI

from app.api import (
    activity,
    alerts,
    analytics,
    auth,
    cron,
    deployments,
    health_checks,
    pull_requests,
    repositories,
    runs,
    webhooks,
)
from app.api.errors import install_github_error_handlers

app = FastAPI(title="DeployLens API", docs_url="/api/docs", openapi_url="/api/openapi.json")

install_github_error_handlers(app)
app.include_router(auth.router)
app.include_router(activity.router)
app.include_router(repositories.router)
app.include_router(deployments.router)
app.include_router(runs.router)
app.include_router(pull_requests.router)
app.include_router(health_checks.router)
app.include_router(analytics.router)
app.include_router(alerts.router)
app.include_router(webhooks.router)
app.include_router(cron.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
