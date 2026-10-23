"""
api/urls.py — URL routing for /api/v1/
"""

from django.urls import path

from api.views import (
    CancelScanView,
    HealthCheckView,
    JobListView,
    JobStatisticsView,
    RemoveScanView,
    ScanResultView,
    ScanStatusView,
    StartScanView,
)

urlpatterns = [
    # ── Health ─────────────────────────────────────────────────────────────
    path("health", HealthCheckView.as_view(), name="health-check"),

    # ── Scan lifecycle ──────────────────────────────────────────────────────
    path("scan/start", StartScanView.as_view(), name="scan-start"),
    path("scan/status/<str:job_id>", ScanStatusView.as_view(), name="scan-status"),
    path("scan/result/<str:job_id>", ScanResultView.as_view(), name="scan-result"),
    path("scan/cancel/<str:job_id>", CancelScanView.as_view(), name="scan-cancel"),
    path("scan/remove/<str:job_id>", RemoveScanView.as_view(), name="scan-remove"),

    # ── Job management ──────────────────────────────────────────────────────
    path("jobs/jobs", JobListView.as_view(), name="job-list"),
    path("jobs/statistics", JobStatisticsView.as_view(), name="job-statistics"),
]
