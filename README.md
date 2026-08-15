# DeployLens

Deployment observability for developers running several projects at once. DeployLens connects to
GitHub, tracks CI/CD activity across your repositories, probes your deployed applications, and
turns both into reliability metrics on a single dashboard.

It answers one question without making you open five tabs: **are my applications deploying
successfully, and are they healthy right now?**

## Architecture

```
GitHub  ──OAuth / REST / Webhooks──►  Vercel  ──►  Neon PostgreSQL
                                    Next.js
                                    FastAPI
```

Both the web app and the API deploy to a single Vercel project as separate services. The API runs
as serverless functions rather than a long-lived process, so there is no server to keep warm.
Scheduled health probes are driven externally and hit a guarded endpoint.

## Stack

| Layer     | Choice                                        |
| --------- | --------------------------------------------- |
| Web       | Next.js 16, React 19, TypeScript, Tailwind 4  |
| API       | FastAPI, Pydantic, SQLAlchemy 2               |
| Database  | Neon (serverless PostgreSQL)                  |
| Auth      | GitHub OAuth                                  |
| Events    | GitHub webhooks                               |
| CI        | GitHub Actions                                |
| Tests     | pytest, Playwright, Vitest                    |

## Local development

Requires Node 24+ and Python 3.12+.

```bash
# Web
cd frontend
npm install
npm run dev

# API
cd backend
py -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/uvicorn.exe app.main:app --reload --port 8000
```

Copy `.env.example` to `.env.local` and fill in the values. `DATABASE_URL` should be Neon's
**pooled** connection string — serverless functions open a connection per invocation, so the
direct endpoint runs out of connections long before the pooled one does.

## Repository layout

```
frontend/    Next.js application
backend/     FastAPI application
  app/       Routes, models, services
  tests/     pytest suite
```
