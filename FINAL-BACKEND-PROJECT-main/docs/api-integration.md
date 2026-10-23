# HubSpot CRM API v3 — Integration Documentation

## Overview

This document describes the HubSpot CRM API v3 integration used by the
HubSpot Deals Extraction Service to extract deal records.

---

## Authentication

**Method:** Private App Access Tokens (recommended over OAuth for server-side integrations)

**How to obtain a token:**
1. Go to [https://developers.hubspot.com/](https://developers.hubspot.com/)
2. Log in to your HubSpot developer account
3. Navigate to **Settings → Integrations → Private Apps**
4. Click **Create a private app**
5. Set app name (e.g., `DLT Deals Extractor`)
6. Under **Scopes**, select: `crm.objects.deals.read`
7. Click **Create app** → copy the generated access token
8. Store the token in a secrets manager — never commit it to version control

**Request Header:**
```
Authorization: Bearer pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Token format:**
- Old format: `pat-na1-<uuid>` (Private App tokens)
- OAuth format: Bearer tokens (starts with `oauth-`)

---

## Base URL

```
https://api.hubapi.com
```

---

## Deals Endpoint

### List Deals

```
GET /crm/v3/objects/deals
```

**Query Parameters:**

| Parameter    | Type    | Required | Default | Description |
|-------------|---------|----------|---------|-------------|
| `limit`     | integer | No       | 10      | Max records per page (1–100) |
| `after`     | string  | No       | —       | Pagination cursor from previous response |
| `properties`| string  | No       | id,hs_object_id | Comma-separated property names |
| `archived`  | boolean | No       | false   | Include archived deals |

**Example Request:**
```bash
curl -X GET \
  "https://api.hubapi.com/crm/v3/objects/deals?limit=100&properties=dealname,amount,dealstage,closedate,pipeline" \
  -H "Authorization: Bearer pat-na1-your-token"
```

**Example Response:**
```json
{
  "results": [
    {
      "id": "12345678",
      "properties": {
        "dealname": "Enterprise Software License",
        "amount": "50000.00",
        "dealstage": "closedwon",
        "closedate": "2024-12-31T00:00:00.000Z",
        "pipeline": "default",
        "hubspot_owner_id": "55123456",
        "createdate": "2024-01-15T09:30:00.000Z",
        "hs_lastmodifieddate": "2024-11-20T14:22:00.000Z",
        "description": "Annual software license renewal",
        "dealtype": "newbusiness"
      },
      "createdAt": "2024-01-15T09:30:00.000Z",
      "updatedAt": "2024-11-20T14:22:00.000Z",
      "archived": false
    }
  ],
  "paging": {
    "next": {
      "after": "NTI1Cg%3D%3D",
      "link": "https://api.hubapi.com/crm/v3/objects/deals?after=NTI1Cg%3D%3D&..."
    }
  }
}
```

---

## Pagination

HubSpot uses **cursor-based pagination**:

1. Make a request with desired `limit`
2. If the response contains `paging.next.after`, there are more pages
3. Pass the `after` value in the next request
4. Repeat until `paging.next` is absent

Our service stores the current `after` cursor in `ExtractionJob.last_cursor` for
checkpoint/resume functionality.

---

## Rate Limits

| Limit Type | Default |
|-----------|---------|
| Requests / 10 seconds | 150 |
| Daily limit | 500,000 (Production) |
| Daily limit | 2,000 (Developer sandbox) |

**Rate limit headers returned by HubSpot:**
- `X-HubSpot-RateLimit-Daily`: Daily limit
- `X-HubSpot-RateLimit-Daily-Remaining`: Remaining daily calls
- `X-HubSpot-RateLimit-Secondly`: Per-second limit

**Our implementation:** Token-bucket sliding-window limiter that tracks request
timestamps and sleeps when approaching the 150 req/10 sec threshold.

---

## Error Responses

| HTTP Status | Meaning | Our Exception |
|------------|---------|--------------|
| 400 | Bad request / invalid property | `HubSpotAPIError` |
| 401 | Invalid or expired access token | `HubSpotAuthError` |
| 403 | Missing required scope | `HubSpotAuthError` |
| 404 | Resource not found | `HubSpotNotFoundError` |
| 429 | Rate limit exceeded | `HubSpotRateLimitError` |
| 5xx | HubSpot server error | `HubSpotAPIError` |

---

## Available Deal Properties

| Property Name | Type | Description |
|--------------|------|-------------|
| `dealname` | string | Name of the deal |
| `amount` | number | Deal amount / value |
| `dealstage` | enumeration | Current pipeline stage |
| `closedate` | datetime | Expected / actual close date |
| `pipeline` | enumeration | Sales pipeline identifier |
| `hubspot_owner_id` | enumeration | Owner's HubSpot user ID |
| `createdate` | datetime | When the deal was created |
| `hs_lastmodifieddate` | datetime | Last modification timestamp |
| `description` | string | Deal description / notes |
| `dealtype` | enumeration | newbusiness / existingbusiness |
| `hs_deal_stage_probability` | number | Win probability (0.0–1.0) |
| `num_associated_contacts` | number | Number of associated contacts |
| `hs_is_closed` | bool | Whether deal is in a closed stage |
| `hs_is_closed_won` | bool | Whether deal closed as won |
| `hs_priority` | enumeration | low / medium / high |
| `hs_forecast_amount` | number | Forecast revenue |
| `num_notes` | number | Number of notes on the deal |
| `hs_object_id` | number | HubSpot object ID (same as deal id) |

---

## Required Scopes

| Scope | Permission |
|-------|-----------|
| `crm.objects.deals.read` | Read deal records |

---

## Integration Notes

- Use `limit=100` (maximum) to minimise the number of API requests
- Request only the properties you need to reduce payload size
- Store the pagination cursor after each page (checkpointing) for fault tolerance
- Never log or persist the raw access token — store only a safe hint
- Test against a HubSpot developer sandbox account, not production
