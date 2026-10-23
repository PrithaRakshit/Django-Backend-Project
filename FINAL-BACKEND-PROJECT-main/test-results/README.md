# Test Results

This directory stores evidence of successful extractions and test runs.

## What to Place Here

After running a real HubSpot extraction, save outputs here:

```
test-results/
├── extraction-logs/
│   └── job-<uuid>.log          Captured server logs during extraction
├── deal-records/
│   └── deals-job-<uuid>.json   JSON dump of the 5 extracted deals
├── screenshots/
│   └── swagger-ui.png          Swagger UI loaded successfully
│   └── health-check.png        Health endpoint response
│   └── deal-results.png        /api/v1/scan/result/ with 5 deals
└── README.md                   This file
```

## How to Save Extraction Output

```bash
# After starting an extraction, capture results
JOB_ID="your-job-uuid-here"

# Save status
curl http://localhost:5200/api/v1/scan/status/$JOB_ID \
  | python3 -m json.tool > test-results/status-$JOB_ID.json

# Save deal records
curl "http://localhost:5200/api/v1/scan/result/$JOB_ID?page_size=100" \
  | python3 -m json.tool > test-results/deals-$JOB_ID.json

# Save statistics
curl http://localhost:5200/api/v1/jobs/statistics \
  | python3 -m json.tool > test-results/statistics.json
```

## Test Run Summary

| Run Date | Token | Job ID | Deals Extracted | Status |
|----------|-------|--------|-----------------|--------|
| (fill in after running) | pat-na1-*** | | | |

## Verified Behaviours

- [ ] 5/5 test deals extracted from HubSpot
- [ ] Health endpoint returns `{"status": "ok"}`
- [ ] Pagination works on `/scan/result/`
- [ ] Cancel endpoint changes status to `cancelled`
- [ ] Remove endpoint returns 404 for subsequent status calls
- [ ] Statistics reflect correct counts and totals
- [ ] Swagger UI accessible at `/api/docs/`
- [ ] OpenAPI schema generates without errors
