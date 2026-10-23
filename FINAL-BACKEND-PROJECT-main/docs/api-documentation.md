# HubSpot Deals Extraction Service — API Documentation

## Overview

The HubSpot Deals Extraction Service exposes a REST API for triggering and
monitoring HubSpot CRM data extraction jobs.

**Base URL (development):** `http://localhost:5200`  
**API prefix:** `/api/v1/`  
**Swagger UI:** `http://localhost:5200/api/docs/`  
**OpenAPI schema:** `http://localhost:5200/api/schema/`

All requests and responses use `application/json`.

---

## Endpoints

### 1. Health Check

**`GET /api/v1/health`**

Returns the service health status. Used by Docker/load balancer health probes.

**Response — 200 OK:**
```json
{
  "status": "ok",
  "service": "hubspot_deals",
  "version": "1.0.0"
}
```

**Example:**
```bash
curl http://localhost:5200/api/v1/health
```

---

### 2. Start Extraction

**`POST /api/v1/scan/start`**

Starts a new async HubSpot deals extraction job.  
Returns immediately with `202 Accepted` and a `job_id` to poll.

**Request Body:**
```json
{
  "access_token": "pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "properties": ["dealname", "amount", "dealstage"],
  "tenant_id": "my-org"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `access_token` | string | **Yes** | HubSpot private-app access token (min 10 chars) |
| `properties` | string[] | No | Deal properties to extract (defaults to standard set) |
| `tenant_id` | string | No | Tenant identifier for multi-tenant isolation |

**Response — 202 Accepted:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Extraction job started. Poll /api/v1/scan/status/<job_id> for progress."
}
```

**Errors:**
- `400` — Missing `access_token` or token too short

**Example:**
```bash
curl -X POST http://localhost:5200/api/v1/scan/start \
  -H "Content-Type: application/json" \
  -d '{"access_token": "pat-na1-your-real-token-here"}'
```

---

### 3. Job Status

**`GET /api/v1/scan/status/{job_id}`**

Poll the current status of an extraction job.

**Response — 200 OK:**
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

**Status values:**

| Status | Description |
|--------|-------------|
| `pending` | Job created, waiting to start |
| `running` | Extraction in progress |
| `completed` | All deals extracted successfully |
| `failed` | Extraction failed — see `error_message` |
| `cancelled` | Cancelled by user request |

**Errors:**
- `404` — Job not found

**Example:**
```bash
curl http://localhost:5200/api/v1/scan/status/550e8400-e29b-41d4-a716-446655440000
```

---

### 4. Fetch Results

**`GET /api/v1/scan/result/{job_id}`**

Retrieve paginated deal records for a **completed** job.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Results per page (default: 20, max: 100) |
| `ordering` | string | Sort field — prefix `-` for descending. Options: `deal_id`, `amount`, `close_date`, `deal_stage`, `extracted_at` |
| `search` | string | Text search across `deal_name`, `deal_stage`, `description` |

**Response — 200 OK:**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "page": 1,
  "total_pages": 1,
  "results": [
    {
      "id": 1,
      "deal_id": "12345678",
      "deal_name": "Enterprise Software License",
      "amount": "50000.00",
      "deal_stage": "closedwon",
      "close_date": "2024-12-31",
      "pipeline": "default",
      "owner_id": "55123456",
      "create_date": "2024-01-15T09:30:00Z",
      "last_modified_date": "2024-11-20T14:22:00Z",
      "description": "Annual software license renewal",
      "deal_type": "newbusiness",
      "extracted_at": "2024-11-01T10:01:45Z",
      "scan_id": "550e8400-e29b-41d4-a716-446655440000",
      "tenant_id": "my-org",
      "raw_properties": { "dealname": "...", "amount": "50000.00" }
    }
  ]
}
```

**Errors:**
- `404` — Job not found
- `409` — Job is not yet completed (status: pending/running/failed/cancelled)

**Example:**
```bash
curl "http://localhost:5200/api/v1/scan/result/550e8400-e29b-41d4-a716-446655440000?page_size=10&ordering=-amount"
```

---

### 5. Cancel Job

**`POST /api/v1/scan/cancel/{job_id}`**

Cancel a pending or running extraction job.

**Response — 200 OK:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled",
  "message": "Job cancelled successfully."
}
```

**Errors:**
- `404` — Job not found
- `409` — Job cannot be cancelled (already completed, failed, or cancelled)

**Example:**
```bash
curl -X POST http://localhost:5200/api/v1/scan/cancel/550e8400-e29b-41d4-a716-446655440000
```

---

### 6. Remove Job

**`DELETE /api/v1/scan/remove/{job_id}`**

Permanently delete a job and all its extracted deal data.  
After deletion, any call to `/status/` or `/result/` for this job will return 404.

**Response — 204 No Content** (empty body)

**Errors:**
- `404` — Job not found

**Example:**
```bash
curl -X DELETE http://localhost:5200/api/v1/scan/remove/550e8400-e29b-41d4-a716-446655440000
```

---

### 7. List Jobs

**`GET /api/v1/jobs/jobs`**

List all extraction jobs with pagination and filtering.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status: `pending/running/completed/failed/cancelled` |
| `pipeline_name` | string | Filter by pipeline name |
| `tenant_id` | string | Filter by tenant |
| `created_after` | datetime | ISO-8601 — only jobs created after this time |
| `created_before` | datetime | ISO-8601 — only jobs created before this time |
| `ordering` | string | Sort by: `created_at`, `-created_at`, `record_count`, `status` |
| `page` | integer | Page number |
| `page_size` | integer | Results per page (max: 100) |

**Response — 200 OK:**
```json
{
  "count": 12,
  "next": "http://localhost:5200/api/v1/jobs/jobs?page=2",
  "previous": null,
  "page": 1,
  "total_pages": 2,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "completed",
      "pipeline_name": "hubspot_deals",
      "tenant_id": "my-org",
      "token_hint": "pat-na1-***",
      "start_time": "2024-11-01T10:00:00Z",
      "end_time": "2024-11-01T10:02:30Z",
      "record_count": 5,
      "last_cursor": null,
      "error_message": null,
      "duration_seconds": 150.0,
      "created_at": "2024-11-01T09:59:55Z",
      "updated_at": "2024-11-01T10:02:30Z"
    }
  ]
}
```

**Example:**
```bash
curl "http://localhost:5200/api/v1/jobs/jobs?status=completed&ordering=-record_count"
```

---

### 8. Job Statistics

**`GET /api/v1/jobs/statistics`**

Returns aggregated metrics across all jobs.

**Response — 200 OK:**
```json
{
  "total_jobs": 15,
  "pending_jobs": 1,
  "running_jobs": 2,
  "completed_jobs": 10,
  "failed_jobs": 1,
  "cancelled_jobs": 1,
  "total_records_extracted": 2500,
  "avg_extraction_time_seconds": 187.5
}
```

**Example:**
```bash
curl http://localhost:5200/api/v1/jobs/statistics
```

---

## Error Response Format

All error responses follow this structure:

```json
{
  "error": "Human-readable error message"
}
```

Or for validation errors (400):

```json
{
  "access_token": ["This field is required."]
}
```

---

## HTTP Status Code Summary

| Code | Meaning |
|------|---------|
| 200 | OK — successful GET or POST |
| 202 | Accepted — job started successfully |
| 204 | No Content — successful DELETE |
| 400 | Bad Request — validation error |
| 404 | Not Found — job does not exist |
| 409 | Conflict — operation not allowed in current state |
| 500 | Internal Server Error — unexpected failure |

---

## Typical Workflow

```
1. POST /api/v1/scan/start          → { job_id: "uuid" }
2. GET  /api/v1/scan/status/uuid    → poll until status == "completed"
3. GET  /api/v1/scan/result/uuid    → retrieve paginated deals
4. GET  /api/v1/jobs/statistics     → view overall metrics
5. DELETE /api/v1/scan/remove/uuid  → clean up when done
```
