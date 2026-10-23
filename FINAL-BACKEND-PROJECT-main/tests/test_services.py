"""
tests/test_services.py

Unit tests for the HubSpot API service and data source.
All external HTTP calls are mocked — no real HubSpot token required.
"""

import threading
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.hubspot_api_service import (
    DEFAULT_DEAL_PROPERTIES,
    HubSpotAPIError,
    HubSpotAPIService,
    HubSpotAuthError,
    HubSpotNotFoundError,
    HubSpotRateLimitError,
)


# ---------------------------------------------------------------------------
# Sample HubSpot API responses
# ---------------------------------------------------------------------------

SAMPLE_DEAL = {
    "id": "12345",
    "properties": {
        "dealname": "Test Deal",
        "amount": "50000.00",
        "dealstage": "closedwon",
        "closedate": "2024-12-31",
        "pipeline": "default",
        "hubspot_owner_id": "owner-1",
        "createdate": "2024-01-01T00:00:00Z",
        "hs_lastmodifieddate": "2024-06-01T00:00:00Z",
        "description": "A test deal",
        "dealtype": "newbusiness",
    },
    "createdAt": "2024-01-01T00:00:00Z",
    "updatedAt": "2024-06-01T00:00:00Z",
    "archived": False,
}

SINGLE_PAGE_RESPONSE = {
    "results": [SAMPLE_DEAL],
    "paging": {},
}

TWO_PAGE_RESPONSE_P1 = {
    "results": [SAMPLE_DEAL],
    "paging": {"next": {"after": "cursor-123"}},
}

TWO_PAGE_RESPONSE_P2 = {
    "results": [
        {**SAMPLE_DEAL, "id": "99999"}
    ],
    "paging": {},
}


# ---------------------------------------------------------------------------
# HubSpotAPIService tests
# ---------------------------------------------------------------------------

class TestHubSpotAPIService:
    """Tests for the HubSpotAPIService HTTP client."""

    def _service(self, access_token="pat-na1-test"):
        return HubSpotAPIService(access_token)

    # -- Credential validation

    def test_validate_credentials_success(self):
        svc = self._service()
        with patch.object(svc, "get_deals", return_value=SINGLE_PAGE_RESPONSE):
            assert svc.validate_credentials() is True

    def test_validate_credentials_raises_auth_error(self):
        svc = self._service()
        with patch.object(svc, "get_deals", side_effect=HubSpotAuthError("Unauthorized", 401)):
            with pytest.raises(HubSpotAuthError):
                svc.validate_credentials()

    # -- get_deals

    def test_get_deals_calls_correct_endpoint(self):
        svc = self._service()
        with patch.object(svc, "_get", return_value=SINGLE_PAGE_RESPONSE) as mock_get:
            svc.get_deals(limit=10)
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert "/crm/v3/objects/deals" in call_args[0][0]

    def test_get_deals_passes_properties(self):
        svc = self._service()
        with patch.object(svc, "_get", return_value=SINGLE_PAGE_RESPONSE) as mock_get:
            svc.get_deals(properties=["dealname", "amount"])
            params = mock_get.call_args[1]["params"]
            assert "dealname" in params["properties"]

    def test_get_deals_limit_capped_at_100(self):
        svc = self._service()
        with patch.object(svc, "_get", return_value=SINGLE_PAGE_RESPONSE) as mock_get:
            svc.get_deals(limit=999)
            params = mock_get.call_args[1]["params"]
            assert params["limit"] == 100

    def test_get_deals_passes_after_cursor(self):
        svc = self._service()
        with patch.object(svc, "_get", return_value=SINGLE_PAGE_RESPONSE) as mock_get:
            svc.get_deals(after="cursor-abc")
            params = mock_get.call_args[1]["params"]
            assert params["after"] == "cursor-abc"

    # -- get_all_deals (pagination)

    def test_get_all_deals_single_page(self):
        svc = self._service()
        with patch.object(svc, "get_deals", return_value=SINGLE_PAGE_RESPONSE):
            deals = list(svc.get_all_deals())
        assert len(deals) == 1
        assert deals[0]["id"] == "12345"

    def test_get_all_deals_multiple_pages(self):
        svc = self._service()
        responses = [TWO_PAGE_RESPONSE_P1, TWO_PAGE_RESPONSE_P2]
        with patch.object(svc, "get_deals", side_effect=responses):
            deals = list(svc.get_all_deals())
        assert len(deals) == 2
        assert deals[0]["id"] == "12345"
        assert deals[1]["id"] == "99999"

    def test_get_all_deals_respects_cancel_event(self):
        cancel = threading.Event()
        cancel.set()  # Signal immediately
        svc = self._service()
        with patch.object(svc, "get_deals", return_value=SINGLE_PAGE_RESPONSE):
            deals = list(svc.get_all_deals(cancel_event=cancel))
        # The cancel event was set before the first iteration so no deals
        assert len(deals) == 0

    # -- Error handling

    def test_handle_401_raises_auth_error(self):
        svc = self._service()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"message": "Unauthorized"}
        with pytest.raises(HubSpotAuthError):
            svc._handle_response_error(mock_resp)

    def test_handle_403_raises_auth_error(self):
        svc = self._service()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"message": "Forbidden"}
        with pytest.raises(HubSpotAuthError):
            svc._handle_response_error(mock_resp)

    def test_handle_404_raises_not_found(self):
        svc = self._service()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"message": "Not found"}
        with pytest.raises(HubSpotNotFoundError):
            svc._handle_response_error(mock_resp)

    def test_handle_429_raises_rate_limit(self):
        svc = self._service()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.json.return_value = {"message": "Too many requests"}
        with pytest.raises(HubSpotRateLimitError):
            svc._handle_response_error(mock_resp)

    def test_handle_500_raises_generic_error(self):
        svc = self._service()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"message": "Server error"}
        with pytest.raises(HubSpotAPIError):
            svc._handle_response_error(mock_resp)

    def test_handle_200_does_not_raise(self):
        svc = self._service()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Should not raise
        svc._handle_response_error(mock_resp)

    # -- Default properties

    def test_default_deal_properties_not_empty(self):
        assert len(DEFAULT_DEAL_PROPERTIES) > 0
        assert "dealname" in DEFAULT_DEAL_PROPERTIES
        assert "amount" in DEFAULT_DEAL_PROPERTIES
        assert "dealstage" in DEFAULT_DEAL_PROPERTIES


# ---------------------------------------------------------------------------
# Data source transformation tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHubSpotDealsDataSource:
    """Tests for the data transformation logic in HubSpotDealsDataSource."""

    def _get_source(self, completed_job):
        from services.data_source import HubSpotDealsDataSource

        return HubSpotDealsDataSource(
            access_token="pat-na1-test",
            job_id=str(completed_job.id),
            checkpoint_every=2,
        )

    def test_transform_deal_basic(self, completed_job):
        from services.data_source import HubSpotDealsDataSource

        source = self._get_source(completed_job)
        job = completed_job
        deal = source._build_deal_object(SAMPLE_DEAL, job)
        assert deal.deal_id == "12345"
        assert deal.deal_name == "Test Deal"
        assert deal.amount == Decimal("50000.00")
        assert deal.deal_stage == "closedwon"
        assert deal.pipeline == "default"

    def test_transform_deal_null_amount(self, completed_job):
        from services.data_source import HubSpotDealsDataSource

        source = self._get_source(completed_job)
        raw = {**SAMPLE_DEAL, "properties": {**SAMPLE_DEAL["properties"], "amount": None}}
        deal = source._build_deal_object(raw, completed_job)
        assert deal.amount is None

    def test_transform_deal_empty_name(self, completed_job):
        from services.data_source import HubSpotDealsDataSource

        source = self._get_source(completed_job)
        raw = {**SAMPLE_DEAL, "properties": {**SAMPLE_DEAL["properties"], "dealname": ""}}
        deal = source._build_deal_object(raw, completed_job)
        assert deal.deal_name is None

    def test_scan_id_matches_job(self, completed_job):
        from services.data_source import HubSpotDealsDataSource

        source = self._get_source(completed_job)
        deal = source._build_deal_object(SAMPLE_DEAL, completed_job)
        assert deal.scan_id == completed_job.id

    def test_tenant_id_copied_from_job(self, db):
        from django.utils import timezone as tz

        from api.models import ExtractionJob
        from services.data_source import HubSpotDealsDataSource

        job = ExtractionJob.objects.create(
            status="running", tenant_id="my-tenant", start_time=tz.now()
        )
        source = HubSpotDealsDataSource("pat-na1-test", str(job.id))
        deal = source._build_deal_object(SAMPLE_DEAL, job)
        assert deal.tenant_id == "my-tenant"
