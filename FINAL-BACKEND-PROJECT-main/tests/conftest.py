"""
tests/conftest.py

Shared pytest fixtures for the HubSpot Deals Extraction Service.
"""

import uuid

import pytest
from django.utils import timezone

from api.models import ExtractionJob, HubSpotDeal


# ---------------------------------------------------------------------------
# Job fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pending_job(db):
    """A freshly created pending ExtractionJob."""
    return ExtractionJob.objects.create(
        status=ExtractionJob.Status.PENDING,
        pipeline_name="hubspot_deals",
        token_hint="pat-na1-***",
    )


@pytest.fixture
def running_job(db):
    """A job currently in the running state."""
    return ExtractionJob.objects.create(
        status=ExtractionJob.Status.RUNNING,
        pipeline_name="hubspot_deals",
        token_hint="pat-na1-***",
        start_time=timezone.now(),
    )


@pytest.fixture
def completed_job(db):
    """A completed job with 5 associated deal records."""
    job = ExtractionJob.objects.create(
        status=ExtractionJob.Status.COMPLETED,
        pipeline_name="hubspot_deals",
        token_hint="pat-na1-***",
        start_time=timezone.now(),
        end_time=timezone.now(),
        record_count=5,
    )
    # Create 5 test deals matching the assessment requirement
    deal_data = [
        ("101", "Deal Alpha", "5000.00", "qualifiedtobuy"),
        ("102", "Deal Beta", "25000.00", "presentationscheduled"),
        ("103", "Deal Gamma", "50000.00", "closedwon"),
        ("104", "Deal Delta", "75000.00", "closedlost"),
        ("105", "Deal Epsilon", "100000.00", "qualifiedtobuy"),
    ]
    for deal_id, name, amount, stage in deal_data:
        HubSpotDeal.objects.create(
            job=job,
            deal_id=deal_id,
            deal_name=name,
            amount=amount,
            deal_stage=stage,
            pipeline="default",
            scan_id=job.id,
            raw_properties={"dealname": name, "amount": amount, "dealstage": stage},
        )
    return job


@pytest.fixture
def failed_job(db):
    """A failed job with an error message."""
    return ExtractionJob.objects.create(
        status=ExtractionJob.Status.FAILED,
        pipeline_name="hubspot_deals",
        token_hint="pat-na1-***",
        start_time=timezone.now(),
        end_time=timezone.now(),
        error_message="Authentication failed: Invalid access token.",
    )


@pytest.fixture
def cancelled_job(db):
    """A cancelled job."""
    return ExtractionJob.objects.create(
        status=ExtractionJob.Status.CANCELLED,
        pipeline_name="hubspot_deals",
        start_time=timezone.now(),
        end_time=timezone.now(),
    )
