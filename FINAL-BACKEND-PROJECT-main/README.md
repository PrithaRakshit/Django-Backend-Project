# HubSpot Deals Extraction Service

A production-quality **Django REST API** that extracts deal records from the HubSpot CRM
(API v3), stores them in a local database, and exposes endpoints for starting jobs,
polling status, retrieving results, and viewing statistics.

Built as part of the Greentree HubSpot DLT Integration assessment.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Features Implemented](#features-implemented)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Prerequisites](#prerequisites)
6. [Setup](#setup)
7. [Environment Variables](#environment-variables)
8. [Database Migrations](#database-migrations)
9. [Sample Data](#sample-data)
10. [Running the Server](#running-the-server)
11. [API Endpoints](#api-endpoints)
12. [Example Requests & Responses](#example-requests--responses)
13. [Swagger UI & OpenAPI Schema](#swagger-ui--openapi-schema)
14. [Running Tests](#running-tests)
15. [Docker](#docker)
16. [Database Notes](#database-notes)
17. [Known Limitations](#known-limitations)
18. [GitHub Upload Instructions](#github-upload-instructions)

---

## Project Overview

This service implements a **HubSpot Deals data extraction pipeline**:

1. A client POSTs a HubSpot private-app access token to `/api/v1/scan/start`
2. The service validates the token and launches a background extraction thread
3. All deal records are fetched via HubSpot CRM API v3 with cursor-based pagination
4. Data is bulk-inserted into SQLite/PostgreSQL with checkpoint support every N pages
5. The client polls `/api/v1/scan/status/<job_id>` until status is `completed`
6. Paginated results are available at `/api/v1/scan/result/<job_id>`

---

## Features Implemented

### Phase 1 — Documentation (`docs/`)
- ✅ `docs/api-integration.md` — HubSpot CRM API v3 details, auth, rate limits, all deal properties
- ✅ `docs/database-schema.md` — PostgreSQL DDL, index design, multi-tenant strategy, type mapping
- ✅ `docs/api-documentation.md` — Full REST API reference with request/response examples

### Phase 2 — Data (Manual step)
- ✅ HubSpot developer account setup instructions in `docs/api-integration.md`
- ✅ Seed script (`scripts/seed_data.py`) creates 5 deals with correct stages/amounts
- ✅ `.env.example` documents access token configuration securely

### Phase 3 — Implementation
- ✅ `services/hubspot_api_service.py` — HubSpot API client with auth, pagination, rate limiting, error handling
- ✅ `services/data_source.py` — Extraction pipeline with cursor checkpointing, transformation, bulk upsert
- ✅ `services/extraction_service.py` — Thread orchestration with cancel signal (threading.Event)
- ✅ Environment configuration with `.env` loading
- ✅ Health endpoint
- ✅ All 8 API endpoints per TEST-GUIDELINES-V1.md
- ✅ Swagger UI and OpenAPI schema
- ✅ 95 automated tests (all passing)
- ✅ Docker support (port 5200)

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.14 |
| Web Framework | Django 6.1 |
| REST Layer | Django REST Framework 3.18 |
| API Docs | drf-spectacular 0.30 |
| Env Loading | python-dotenv |
| Filtering | django-filter |
| HTTP Client | requests |
| Testing | pytest 8.4 + pytest-django |
| Database | SQLite (dev) / PostgreSQL (production) |
| Background Jobs | Python threading (stdlib) |
| Container | Docker + docker-compose |

---

## Project Structure

```
danjo project/
├── manage.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── pytest.ini
├── docker-compose.yml
├── Dockerfile
├── config/
│   ├── settings.py         Django settings (env-driven)
│   ├── urls.py             Root URL config
│   ├── asgi.py / wsgi.py
├── api/
│   ├── models.py           ExtractionJob, HubSpotDeal
│   ├── serializers.py      DRF serializers + request/response schemas
│   ├── views.py            All 8 API views
│   ├── urls.py             /api/v1/ routes
│   ├── pagination.py       Standard paginator
│   ├── filters.py          django-filter FilterSets
│   ├── admin.py            Admin registration
│   └── migrations/         Database migrations
├── services/
│   ├── hubspot_api_service.py   HubSpot CRM API v3 client
│   ├── data_source.py           Extraction + checkpoint + transformation
│   └── extraction_service.py    Thread orchestration + cancel
├── tests/
│   ├── conftest.py         Shared fixtures
│   ├── test_models.py      Model tests (20 tests)
│   ├── test_api.py         API endpoint tests (52 tests)
│   └── test_services.py    Service unit tests (23 tests)
├── docs/
│   ├── api-integration.md  HubSpot CRM API docs
│   ├── database-schema.md  PostgreSQL schema + DDL
│   └── api-documentation.md   Service REST API reference
├── scripts/
│   └── seed_data.py        Seeds 5 demo deals
└── test-results/
    └── README.md           Placeholder for extraction logs/screenshots
```

---

## Prerequisites

- Python 3.11+ (Python 3.14 tested)
- pip
- (Optional) Docker + Docker Compose for containerised deployment
- A HubSpot developer account with a private app access token

---

## Setup

### 1. Clone / navigate to the project

```bash
cd "danjo project"
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
SECRET_KEY=your-long-random-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Leave empty to use SQLite (local dev)
# DATABASE_URL=postgresql://user:password@localhost:5432/hubspot_deals

HUBSPOT_BASE_URL=https://api.hubapi.com
HUBSPOT_TIMEOUT=30

PIPELINE_NAME=hubspot_deals
CHECKPOINT_EVERY=5
SERVICE_PORT=5200
```

> ⚠️ Never add a real HubSpot access token to `.env.example` or commit `.env` to git.

---

## Database Migrations

```bash
python manage.py migrate
```

### Create a superuser (optional, for Django admin at `/admin/`)

```bash
python manage.py createsuperuser
```

---

## Sample Data

Seed 5 demo deals + example jobs for local exploration:

```bash
python scripts/seed_data.py
```

This creates:
- 1 completed job with 5 deals ($5K, $25K, $50K, $75K, $100K across multiple stages)
- 1 pending job
- 1 failed job

---

## Running the Server

```bash
python manage.py runserver 5200
```

The server will be available at `http://localhost:5200`.

**Or with Docker:**

```bash
docker-compose up --build
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Service health check |
| POST | `/api/v1/scan/start` | Start a HubSpot extraction job |
| GET | `/api/v1/scan/status/<job_id>` | Poll job status |
| GET | `/api/v1/scan/result/<job_id>` | Get paginated deal results |
| POST | `/api/v1/scan/cancel/<job_id>` | Cancel a pending/running job |
| DELETE | `/api/v1/scan/remove/<job_id>` | Delete job and all data |
| GET | `/api/v1/jobs/jobs` | List all jobs (filterable, paginated) |
| GET | `/api/v1/jobs/statistics` | Aggregated statistics |
| GET | `/api/schema/` | OpenAPI schema (JSON/YAML) |
| GET | `/api/docs/` | Swagger UI |

---

## Example Requests & Responses

### Health Check

```bash
curl http://localhost:5200/api/v1/health
```

```json
{ "status": "ok", "service": "hubspot_deals", "version": "1.0.0" }
```

### Start an Extraction

```bash
curl -X POST http://localhost:5200/api/v1/scan/start \
  -H "Content-Type: application/json" \
  -d '{"access_token": "pat-na1-your-real-token-here"}'
```

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Extraction job started. Poll /api/v1/scan/status/<job_id> for progress."
}
```

### Poll Status

```bash
curl http://localhost:5200/api/v1/scan/status/550e8400-e29b-41d4-a716-446655440000
```

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "record_count": 5,
  "start_time": "2024-11-01T10:00:00Z",
  "end_time": "2024-11-01T10:02:30Z",
  "pipeline_name": "hubspot_deals",
  "error_message": null,
  "duration_seconds": 150.0
}
```

### Get Results

```bash
curl "http://localhost:5200/api/v1/scan/result/550e8400-e29b-41d4-a716-446655440000?ordering=-amount&page_size=5"
```

### List All Jobs

```bash
curl "http://localhost:5200/api/v1/jobs/jobs?status=completed&ordering=-record_count"
```

### Statistics

```bash
curl http://localhost:5200/api/v1/jobs/statistics
```

```json
{
  "total_jobs": 3,
  "pending_jobs": 1,
  "running_jobs": 0,
  "completed_jobs": 1,
  "failed_jobs": 1,
  "cancelled_jobs": 0,
  "total_records_extracted": 5,
  "avg_extraction_time_seconds": 150.0
}
```

---

## Swagger UI & OpenAPI Schema

| URL | Description |
|-----|-------------|
| `http://localhost:5200/api/docs/` | Interactive Swagger UI |
| `http://localhost:5200/api/schema/` | OpenAPI 3.x schema (JSON) |
| `http://localhost:5200/api/schema/?format=yaml` | OpenAPI 3.x schema (YAML) |

Export the schema to a file:

```bash
python manage.py spectacular --file schema.yml
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Specific file
pytest tests/test_api.py -v

# With coverage (requires pytest-cov)
pytest tests/ --cov=api --cov=services --cov-report=term-missing
```

Expected output: **95 tests, 0 failures**

---

## Docker

### Build and start (port 5200)

```bash
docker-compose up --build
```

### Health check

```bash
curl http://localhost:5200/api/v1/health
```

### Run migrations inside container

```bash
docker-compose exec web python manage.py migrate
```

### Stop

```bash
docker-compose down
```

---

## Database Notes

- **Local development:** Uses SQLite (`db.sqlite3`) — zero configuration needed
- **Production / Docker:** Set `DATABASE_URL=postgresql://user:password@host:5432/dbname`
- Migrations handle all schema changes — never edit migration files manually
- The `db.sqlite3` file is excluded from git by `.gitignore`

---

## Known Limitations

1. **In-process threading:** Background extraction uses Python daemon threads — not shared across
   multiple Django worker processes. For multi-worker production deployments, replace with
   Celery + Redis/RabbitMQ.

2. **No authentication layer on endpoints:** The API is unauthenticated by design
   (the HubSpot token is job-level, not request-level). Add API key or JWT auth
   for multi-user deployments.

3. **SQLite concurrency:** SQLite has write serialisation — fine for single-user dev,
   but use PostgreSQL for concurrent workloads.

4. **HubSpot token not persisted:** Only a safe hint (`pat-na1-***`) is stored.
   If the process restarts mid-job, the job resumes from the last checkpoint cursor
   but needs a new token via the cancel + restart flow.

---

## GitHub Upload Instructions

```bash
# 1. Initialise git in the project directory (if not already)
git init

# 2. Stage all project files (secrets are excluded by .gitignore)
git add .

# 3. Verify .env is NOT staged
git status | grep .env     # Should return nothing

# 4. Commit
git commit -m "feat: complete HubSpot Deals Extraction Service"

# 5. Create a new repository on GitHub (via github.com) — do NOT initialise with README

# 6. Add the remote origin
git remote add origin https://github.com/<your-username>/<your-repo>.git

# 7. Push
git branch -M main
git push -u origin main
```

> ✅ Pre-push checklist:
> - [ ] `.env` is NOT in git (`git status` shows no `.env`)
> - [ ] `db.sqlite3` is NOT in git
> - [ ] `venv/` is NOT in git
> - [ ] `requirements.txt` IS committed
> - [ ] `README.md` IS committed
> - [ ] `.env.example` IS committed
> - [ ] All tests pass (`pytest tests/ -v`)
