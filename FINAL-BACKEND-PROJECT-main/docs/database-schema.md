# Database Schema Documentation

## Overview

This document describes the database schema used by the HubSpot Deals Extraction Service.

The service uses **SQLite** for local development and **PostgreSQL** for staging/production.
The schema is managed by Django migrations.

---

## Tables

### `api_extractionjob`

Tracks the lifecycle of each data extraction job.

```sql
CREATE TABLE api_extractionjob (
    id              UUID            PRIMARY KEY,
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending',
                                    -- Values: pending | running | completed | failed | cancelled
    pipeline_name   VARCHAR(100)    NOT NULL DEFAULT 'hubspot_deals',
    tenant_id       VARCHAR(100)    NULL,
    token_hint      VARCHAR(30)     NULL,    -- e.g. "pat-na1-***"
    start_time      TIMESTAMPTZ     NULL,
    end_time        TIMESTAMPTZ     NULL,
    record_count    INTEGER         NOT NULL DEFAULT 0,
    last_cursor     VARCHAR(500)    NULL,    -- HubSpot pagination checkpoint cursor
    error_message   TEXT            NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_extractionjob_status_created   ON api_extractionjob (status, created_at);
CREATE INDEX idx_extractionjob_tenant_status    ON api_extractionjob (tenant_id, status);
CREATE INDEX idx_extractionjob_status           ON api_extractionjob (status);
CREATE INDEX idx_extractionjob_tenant_id        ON api_extractionjob (tenant_id);
```

**Field Notes:**
- `id`: UUID primary key — safe to expose in API responses, globally unique
- `status`: Represents the job state machine: `pending → running → completed/failed/cancelled`
- `token_hint`: Only the first 8 characters of the HubSpot access token + `***` — never store the real token
- `last_cursor`: HubSpot's cursor-based `after` value saved every N pages for checkpoint/resume
- `record_count`: Updated incrementally during extraction (progress indicator)

---

### `api_hubspotdeal`

Stores individual deal records extracted from HubSpot CRM.

```sql
CREATE TABLE api_hubspotdeal (
    id                  BIGSERIAL       PRIMARY KEY,
    job_id              UUID            NOT NULL REFERENCES api_extractionjob(id) ON DELETE CASCADE,
    deal_id             VARCHAR(100)    NOT NULL,
    deal_name           VARCHAR(500)    NULL,
    amount              DECIMAL(15, 2)  NULL,
    deal_stage          VARCHAR(100)    NULL,
    close_date          DATE            NULL,
    pipeline            VARCHAR(100)    NULL,
    owner_id            VARCHAR(100)    NULL,
    create_date         TIMESTAMPTZ     NULL,
    last_modified_date  TIMESTAMPTZ     NULL,
    description         TEXT            NULL,
    deal_type           VARCHAR(100)    NULL,

    -- ETL metadata (DLT convention)
    extracted_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    scan_id             UUID            NOT NULL,
    tenant_id           VARCHAR(100)    NULL,
    raw_properties      JSONB           NOT NULL DEFAULT '{}',

    CONSTRAINT uq_deal_per_job UNIQUE (job_id, deal_id)
);

-- Indexes
CREATE INDEX idx_hubspotdeal_deal_stage  ON api_hubspotdeal (deal_stage);
CREATE INDEX idx_hubspotdeal_close_date  ON api_hubspotdeal (close_date);
CREATE INDEX idx_hubspotdeal_tenant_id   ON api_hubspotdeal (tenant_id);
CREATE INDEX idx_hubspotdeal_deal_id     ON api_hubspotdeal (deal_id);
```

**Field Notes:**
- `job_id`: Foreign key to `api_extractionjob`; cascading delete removes all deals when a job is removed
- `deal_id`: HubSpot's numeric string deal identifier
- `scan_id`: Mirrors `job_id` for ETL pipeline compatibility (DLT convention: `_scan_id`)
- `tenant_id`: Copied from the parent job for multi-tenant isolation without joins
- `raw_properties`: Full JSONB dump of all HubSpot properties for forward-compatibility
- `UNIQUE (job_id, deal_id)`: Prevents duplicate extraction within the same job (idempotent)

---

## HubSpot → Database Type Mapping

| HubSpot Type | HubSpot Example | PostgreSQL Type | Django Field |
|-------------|----------------|-----------------|--------------|
| `string` | `"Enterprise Deal"` | `VARCHAR(500)` | `CharField` |
| `number` | `"50000.00"` | `DECIMAL(15,2)` | `DecimalField` |
| `enumeration` | `"closedwon"` | `VARCHAR(100)` | `CharField` |
| `datetime` | `"2024-01-15T09:30:00.000Z"` | `TIMESTAMPTZ` | `DateTimeField` |
| `date` | `"2024-12-31"` | `DATE` | `DateField` |
| `bool` | `"true"` | `BOOLEAN` | `BooleanField` (not used; stored in raw_properties) |
| `json_object` | `{...}` | `JSONB` | `JSONField` |

---

## Multi-Tenant Design

The service supports multi-tenant deployments via `tenant_id`:

- Each `ExtractionJob` can carry an optional `tenant_id`
- `tenant_id` is propagated to all `HubSpotDeal` records
- All list/filter endpoints support `?tenant_id=` filtering
- Data isolation is logical (same tables, filtered queries)
- For physical isolation, deploy separate database schemas per tenant

**Recommended PostgreSQL index for multi-tenant workloads:**
```sql
CREATE INDEX idx_hubspotdeal_tenant_stage
    ON api_hubspotdeal (tenant_id, deal_stage);
```

---

## Performance Considerations

- `JSONB` (`raw_properties`) is indexed implicitly in PostgreSQL; add GIN index if you query inside JSON
- The `unique_together` constraint on `(job_id, deal_id)` doubles as an index
- `bulk_create(ignore_conflicts=True)` is used for bulk inserts — significantly faster than row-by-row saves
- No N+1 query problems: `ScanResultView` queries deals directly; no nested loops

---

## SQLite Notes (Local Development)

- SQLite does not support `TIMESTAMPTZ`; Django handles timezone conversion transparently
- SQLite does not support `JSONB`; Django stores JSON as `TEXT` and deserialises on read
- SQLite UUID support: stored as `VARCHAR(32)`
- For production, use PostgreSQL — set `DATABASE_URL=postgresql://...` in `.env`
