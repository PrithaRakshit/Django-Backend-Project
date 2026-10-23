"""
tests/test_models.py

Unit tests for ExtractionJob and HubSpotDeal Django models.
Covers: creation, constraints, status choices, helper methods, and relationships.
"""

import uuid

import pytest
from django.db import IntegrityError
from django.utils import timezone

from api.models import ExtractionJob, HubSpotDeal


@pytest.mark.django_db
class TestExtractionJobModel:
    """Tests for the ExtractionJob model."""

    def test_create_job_with_defaults(self):
        """Creating a job without explicit fields uses sensible defaults."""
        job = ExtractionJob.objects.create()
        assert job.status == ExtractionJob.Status.PENDING
        assert job.pipeline_name == "hubspot_deals"
        assert job.record_count == 0
        assert job.start_time is None
        assert job.end_time is None
        assert job.error_message is None
        assert job.last_cursor is None
        assert job.id is not None

    def test_job_id_is_uuid(self):
        """Job primary key is a UUID."""
        job = ExtractionJob.objects.create()
        assert isinstance(job.id, uuid.UUID)

    def test_status_choices(self):
        """All five status values are accepted."""
        for s in ("pending", "running", "completed", "failed", "cancelled"):
            job = ExtractionJob.objects.create(status=s)
            assert job.status == s

    def test_make_token_hint_masks_token(self):
        """make_token_hint returns first 8 chars + ***."""
        hint = ExtractionJob.make_token_hint("pat-na1-abcdefgh-xxxx")
        assert hint == "pat-na1-***"
        assert "abcdefgh" not in hint

    def test_make_token_hint_short_token(self):
        """Very short tokens are fully masked."""
        assert ExtractionJob.make_token_hint("abc") == "***"

    def test_duration_seconds_completed(self):
        """duration_seconds returns correct wall-clock time."""
        now = timezone.now()
        job = ExtractionJob.objects.create(
            status="completed",
            start_time=now,
            end_time=now,
        )
        # Same start/end → 0 seconds
        assert job.duration_seconds == 0.0

    def test_duration_seconds_none_when_not_finished(self):
        """duration_seconds is None when end_time is not set."""
        job = ExtractionJob.objects.create(start_time=timezone.now())
        assert job.duration_seconds is None

    def test_ordering_newest_first(self):
        """Default ordering is -created_at."""
        j1 = ExtractionJob.objects.create()
        j2 = ExtractionJob.objects.create()
        jobs = list(ExtractionJob.objects.all())
        assert jobs[0].id == j2.id  # newest first

    def test_tenant_id_can_be_null(self):
        """tenant_id is optional."""
        job = ExtractionJob.objects.create(tenant_id=None)
        assert job.tenant_id is None

    def test_str_representation(self):
        """__str__ includes id and status."""
        job = ExtractionJob.objects.create(status="running")
        assert "running" in str(job)


@pytest.mark.django_db
class TestHubSpotDealModel:
    """Tests for the HubSpotDeal model."""

    def test_create_deal(self, completed_job):
        """A deal can be created and retrieved."""
        deal = HubSpotDeal.objects.filter(job=completed_job).first()
        assert deal is not None
        assert deal.deal_id in ("101", "102", "103", "104", "105")

    def test_deal_has_five_records(self, completed_job):
        """The completed_job fixture has exactly 5 deals."""
        assert HubSpotDeal.objects.filter(job=completed_job).count() == 5

    def test_deal_fk_to_job(self, completed_job):
        """HubSpotDeal.job references the parent ExtractionJob."""
        deal = HubSpotDeal.objects.filter(job=completed_job).first()
        assert deal.job == completed_job

    def test_unique_together_deal_id_per_job(self, completed_job):
        """Cannot create two deals with the same deal_id for the same job."""
        with pytest.raises(IntegrityError):
            HubSpotDeal.objects.create(
                job=completed_job,
                deal_id="101",  # Already exists in this job
                scan_id=completed_job.id,
            )

    def test_cascade_delete(self, completed_job):
        """Deleting the job cascades to its deals."""
        job_id = completed_job.id
        completed_job.delete()
        assert HubSpotDeal.objects.filter(job_id=job_id).count() == 0

    def test_deal_amount_is_decimal(self, completed_job):
        """amount field stores as Decimal."""
        from decimal import Decimal

        deal = HubSpotDeal.objects.get(job=completed_job, deal_id="103")
        assert deal.amount == Decimal("50000.00")

    def test_deal_stage_stored_correctly(self, completed_job):
        """deal_stage is persisted and retrievable."""
        deal = HubSpotDeal.objects.get(job=completed_job, deal_id="103")
        assert deal.deal_stage == "closedwon"

    def test_scan_id_matches_job_id(self, completed_job):
        """scan_id field mirrors the parent job's UUID."""
        deal = HubSpotDeal.objects.filter(job=completed_job).first()
        assert deal.scan_id == completed_job.id

    def test_raw_properties_json_field(self, completed_job):
        """raw_properties is a JSONField storing a dict."""
        deal = HubSpotDeal.objects.filter(job=completed_job).first()
        assert isinstance(deal.raw_properties, dict)

    def test_null_amount_is_allowed(self, completed_job):
        """Deals without an amount are allowed (nullable field)."""
        deal = HubSpotDeal.objects.create(
            job=completed_job,
            deal_id="999",
            amount=None,
            scan_id=completed_job.id,
        )
        assert deal.amount is None
