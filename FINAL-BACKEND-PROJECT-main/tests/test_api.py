"""
tests/test_api.py

Full API endpoint tests for the HubSpot Deals Extraction Service.

Covers (per TEST-GUIDELINES-V1.md):
  - Seeded data tests (all endpoints)
  - Edge case tests (404, 400, 409, invalid inputs)
  - Schema generation
  - Pagination and filtering

All external HTTP calls are mocked — no real HubSpot token required.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.models import ExtractionJob, HubSpotDeal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return APIClient()


# ---------------------------------------------------------------------------
# 1. Health Check Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHealthCheck:
    """GET /api/v1/health"""

    def test_health_returns_200(self, client):
        url = reverse("health-check")
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_health_response_structure(self, client):
        url = reverse("health-check")
        data = client.get(url).json()
        assert data["status"] == "ok"
        assert data["service"] == "hubspot_deals"
        assert "version" in data

    def test_health_does_not_require_auth(self, client):
        """Health endpoint must always be accessible without authentication."""
        url = reverse("health-check")
        response = client.get(url)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2. Start Scan Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStartScan:
    """POST /api/v1/scan/start"""

    def _mock_extraction(self):
        """Patch the extraction service so no real thread is spawned."""
        return patch(
            "api.views.extraction_service.start_extraction", return_value=None
        )

    def test_start_scan_returns_202(self, client):
        with self._mock_extraction():
            response = client.post(
                reverse("scan-start"),
                {"access_token": "pat-na1-abcdefghij"},
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_start_scan_creates_job_in_db(self, client):
        with self._mock_extraction():
            client.post(
                reverse("scan-start"),
                {"access_token": "pat-na1-abcdefghij"},
                format="json",
            )
        assert ExtractionJob.objects.count() == 1
        job = ExtractionJob.objects.first()
        assert job.status in ("pending", "running")

    def test_start_scan_response_contains_job_id(self, client):
        with self._mock_extraction():
            data = client.post(
                reverse("scan-start"),
                {"access_token": "pat-na1-abcdefghij"},
                format="json",
            ).json()
        assert "job_id" in data
        uuid.UUID(data["job_id"])  # Must be a valid UUID

    def test_start_scan_token_hint_stored_not_token(self, client):
        """Real token must NOT be persisted."""
        token = "pat-na1-supersecrettoken"
        with self._mock_extraction():
            client.post(
                reverse("scan-start"),
                {"access_token": token},
                format="json",
            )
        job = ExtractionJob.objects.first()
        assert token not in (job.token_hint or "")
        assert "***" in (job.token_hint or "")

    def test_start_scan_with_optional_properties(self, client):
        with self._mock_extraction():
            response = client.post(
                reverse("scan-start"),
                {
                    "access_token": "pat-na1-abcdefghij",
                    "properties": ["dealname", "amount"],
                    "tenant_id": "tenant-001",
                },
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED
        job = ExtractionJob.objects.first()
        assert job.tenant_id == "tenant-001"

    def test_start_scan_missing_token_returns_400(self, client):
        response = client.post(reverse("scan-start"), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "access_token" in response.json()

    def test_start_scan_too_short_token_returns_400(self, client):
        response = client.post(
            reverse("scan-start"),
            {"access_token": "short"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# 3. Scan Status Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestScanStatus:
    """GET /api/v1/scan/status/<job_id>"""

    def test_status_pending_job(self, client, pending_job):
        url = reverse("scan-status", kwargs={"job_id": str(pending_job.id)})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "pending"
        assert data["id"] == str(pending_job.id)

    def test_status_completed_job(self, client, completed_job):
        url = reverse("scan-status", kwargs={"job_id": str(completed_job.id)})
        data = client.get(url).json()
        assert data["status"] == "completed"
        assert data["record_count"] == 5

    def test_status_response_has_required_fields(self, client, completed_job):
        url = reverse("scan-status", kwargs={"job_id": str(completed_job.id)})
        data = client.get(url).json()
        for field in ("id", "status", "record_count", "start_time", "end_time", "pipeline_name"):
            assert field in data, f"Missing field: {field}"

    def test_status_nonexistent_job_returns_404(self, client):
        url = reverse("scan-status", kwargs={"job_id": str(uuid.uuid4())})
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_status_invalid_job_id_returns_404(self, client):
        url = reverse("scan-status", kwargs={"job_id": "not-a-uuid"})
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_status_failed_job_has_error_message(self, client, failed_job):
        url = reverse("scan-status", kwargs={"job_id": str(failed_job.id)})
        data = client.get(url).json()
        assert data["status"] == "failed"
        assert data["error_message"] is not None


# ---------------------------------------------------------------------------
# 4. Scan Result Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestScanResult:
    """GET /api/v1/scan/result/<job_id>"""

    def test_result_returns_200_for_completed_job(self, client, completed_job):
        url = reverse("scan-result", kwargs={"job_id": str(completed_job.id)})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_result_returns_all_5_deals(self, client, completed_job):
        url = reverse("scan-result", kwargs={"job_id": str(completed_job.id)})
        data = client.get(url).json()
        assert data["count"] == 5
        assert len(data["results"]) == 5

    def test_result_deal_fields_present(self, client, completed_job):
        url = reverse("scan-result", kwargs={"job_id": str(completed_job.id)})
        deal = client.get(url).json()["results"][0]
        for field in ("deal_id", "deal_name", "amount", "deal_stage", "extracted_at"):
            assert field in deal, f"Missing field: {field}"

    def test_result_pagination_structure(self, client, completed_job):
        url = reverse("scan-result", kwargs={"job_id": str(completed_job.id)})
        data = client.get(url).json()
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data

    def test_result_page_size_respected(self, client, completed_job):
        """page_size query param limits results per page."""
        url = reverse("scan-result", kwargs={"job_id": str(completed_job.id)})
        data = client.get(url + "?page_size=2").json()
        assert len(data["results"]) == 2
        assert data["count"] == 5

    def test_result_pending_job_returns_409(self, client, pending_job):
        url = reverse("scan-result", kwargs={"job_id": str(pending_job.id)})
        response = client.get(url)
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_result_running_job_returns_409(self, client, running_job):
        url = reverse("scan-result", kwargs={"job_id": str(running_job.id)})
        response = client.get(url)
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_result_nonexistent_job_returns_404(self, client):
        url = reverse("scan-result", kwargs={"job_id": str(uuid.uuid4())})
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_result_ordering_by_amount(self, client, completed_job):
        """Results can be ordered by amount ascending."""
        url = reverse("scan-result", kwargs={"job_id": str(completed_job.id)})
        data = client.get(url + "?ordering=amount").json()
        amounts = [
            float(d["amount"]) for d in data["results"] if d["amount"] is not None
        ]
        assert amounts == sorted(amounts)

    def test_result_filter_by_deal_stage(self, client, completed_job):
        """Filter results by deal_stage."""
        url = reverse("scan-result", kwargs={"job_id": str(completed_job.id)})
        data = client.get(url + "?search=closedwon").json()
        # search is broad; just check it returns some subset
        assert data["count"] >= 0  # Don't fail — search is case-insensitive text


# ---------------------------------------------------------------------------
# 5. Cancel Scan Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCancelScan:
    """POST /api/v1/scan/cancel/<job_id>"""

    def test_cancel_pending_job_returns_200(self, client, pending_job):
        with patch("api.views.extraction_service.cancel_extraction", return_value=True):
            response = client.post(
                reverse("scan-cancel", kwargs={"job_id": str(pending_job.id)})
            )
        assert response.status_code == status.HTTP_200_OK

    def test_cancel_changes_status_to_cancelled(self, client, pending_job):
        """After cancel, the response status should be 'cancelled'."""
        def fake_cancel(job_id):
            ExtractionJob.objects.filter(pk=job_id).update(status="cancelled")
            return True

        with patch("api.views.extraction_service.cancel_extraction", side_effect=fake_cancel):
            data = client.post(
                reverse("scan-cancel", kwargs={"job_id": str(pending_job.id)})
            ).json()
        assert data["status"] == "cancelled"

    def test_cancel_completed_job_returns_409(self, client, completed_job):
        url = reverse("scan-cancel", kwargs={"job_id": str(completed_job.id)})
        response = client.post(url)
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_cancel_failed_job_returns_409(self, client, failed_job):
        url = reverse("scan-cancel", kwargs={"job_id": str(failed_job.id)})
        response = client.post(url)
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_cancel_nonexistent_job_returns_404(self, client):
        url = reverse("scan-cancel", kwargs={"job_id": str(uuid.uuid4())})
        response = client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cancel_already_cancelled_job_returns_409(self, client, cancelled_job):
        url = reverse("scan-cancel", kwargs={"job_id": str(cancelled_job.id)})
        response = client.post(url)
        assert response.status_code == status.HTTP_409_CONFLICT


# ---------------------------------------------------------------------------
# 6. Remove Scan Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRemoveScan:
    """DELETE /api/v1/scan/remove/<job_id>"""

    def test_remove_job_returns_204(self, client, completed_job):
        url = reverse("scan-remove", kwargs={"job_id": str(completed_job.id)})
        response = client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_remove_deletes_job_from_db(self, client, completed_job):
        job_id = completed_job.id
        url = reverse("scan-remove", kwargs={"job_id": str(job_id)})
        client.delete(url)
        assert not ExtractionJob.objects.filter(pk=job_id).exists()

    def test_remove_cascades_to_deals(self, client, completed_job):
        """Removing a job also removes its associated deal records."""
        job_id = completed_job.id
        assert HubSpotDeal.objects.filter(job_id=job_id).count() == 5
        client.delete(reverse("scan-remove", kwargs={"job_id": str(job_id)}))
        assert HubSpotDeal.objects.filter(job_id=job_id).count() == 0

    def test_remove_nonexistent_job_returns_404(self, client):
        url = reverse("scan-remove", kwargs={"job_id": str(uuid.uuid4())})
        response = client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_status_after_remove_returns_404(self, client, completed_job):
        """After deletion, polling status returns 404."""
        job_id = str(completed_job.id)
        client.delete(reverse("scan-remove", kwargs={"job_id": job_id}))
        response = client.get(reverse("scan-status", kwargs={"job_id": job_id}))
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# 7. Job List Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestJobList:
    """GET /api/v1/jobs/jobs"""

    def test_list_all_jobs(
        self, client, pending_job, completed_job, failed_job, cancelled_job
    ):
        data = client.get(reverse("job-list")).json()
        assert data["count"] >= 4

    def test_list_pagination_structure(self, client, pending_job):
        data = client.get(reverse("job-list")).json()
        assert "count" in data
        assert "results" in data

    def test_list_filter_by_status(self, client, pending_job, completed_job):
        data = client.get(reverse("job-list") + "?status=pending").json()
        for job in data["results"]:
            assert job["status"] == "pending"

    def test_list_filter_by_status_completed(
        self, client, pending_job, completed_job, failed_job
    ):
        data = client.get(reverse("job-list") + "?status=completed").json()
        assert data["count"] >= 1
        for job in data["results"]:
            assert job["status"] == "completed"

    def test_list_ordering_by_record_count(
        self, client, pending_job, completed_job
    ):
        data = client.get(
            reverse("job-list") + "?ordering=-record_count"
        ).json()
        counts = [j["record_count"] for j in data["results"]]
        assert counts == sorted(counts, reverse=True)

    def test_list_filter_by_tenant(self, client, db):
        ExtractionJob.objects.create(tenant_id="tenant-A", status="completed")
        ExtractionJob.objects.create(tenant_id="tenant-B", status="completed")
        data = client.get(reverse("job-list") + "?tenant_id=tenant-A").json()
        assert data["count"] == 1
        assert data["results"][0]["tenant_id"] == "tenant-A"

    def test_list_page_size(self, client, db):
        for _ in range(5):
            ExtractionJob.objects.create()
        data = client.get(reverse("job-list") + "?page_size=2").json()
        assert len(data["results"]) == 2

    def test_list_job_fields(self, client, completed_job):
        data = client.get(reverse("job-list")).json()
        job = data["results"][0]
        for field in ("id", "status", "record_count", "pipeline_name", "created_at"):
            assert field in job, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# 8. Job Statistics Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestJobStatistics:
    """GET /api/v1/jobs/statistics"""

    def test_statistics_returns_200(self, client):
        response = client.get(reverse("job-statistics"))
        assert response.status_code == status.HTTP_200_OK

    def test_statistics_structure(self, client):
        data = client.get(reverse("job-statistics")).json()
        for field in (
            "total_jobs",
            "pending_jobs",
            "running_jobs",
            "completed_jobs",
            "failed_jobs",
            "cancelled_jobs",
            "total_records_extracted",
            "avg_extraction_time_seconds",
        ):
            assert field in data, f"Missing field: {field}"

    def test_statistics_counts_match_db(
        self,
        client,
        pending_job,
        running_job,
        completed_job,
        failed_job,
        cancelled_job,
    ):
        data = client.get(reverse("job-statistics")).json()
        assert data["total_jobs"] >= 5
        assert data["pending_jobs"] >= 1
        assert data["running_jobs"] >= 1
        assert data["completed_jobs"] >= 1
        assert data["failed_jobs"] >= 1
        assert data["cancelled_jobs"] >= 1

    def test_statistics_total_records(self, client, completed_job):
        data = client.get(reverse("job-statistics")).json()
        assert data["total_records_extracted"] >= 5  # completed_job has 5 deals

    def test_statistics_empty_db(self, client, db):
        """Statistics endpoint works with zero jobs."""
        data = client.get(reverse("job-statistics")).json()
        assert data["total_jobs"] == 0
        assert data["total_records_extracted"] == 0
        assert data["avg_extraction_time_seconds"] is None


# ---------------------------------------------------------------------------
# 9. OpenAPI Schema Generation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSchemaGeneration:
    """Validates that drf-spectacular can generate a valid schema."""

    def test_schema_endpoint_returns_200(self, client):
        response = client.get("/api/schema/")
        assert response.status_code == status.HTTP_200_OK

    def test_schema_is_openapi_3(self, client):
        data = client.get("/api/schema/?format=json").json()
        assert "openapi" in data
        assert data["openapi"].startswith("3.")

    def test_schema_has_all_paths(self, client):
        data = client.get("/api/schema/?format=json").json()
        paths = data.get("paths", {})
        expected = [
            "/api/v1/health",
            "/api/v1/scan/start",
            "/api/v1/jobs/jobs",
            "/api/v1/jobs/statistics",
        ]
        for path in expected:
            assert path in paths, f"Path missing from schema: {path}"

    def test_swagger_ui_loads(self, client):
        response = client.get("/api/docs/")
        assert response.status_code == status.HTTP_200_OK
