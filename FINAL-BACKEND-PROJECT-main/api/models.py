"""
Django models for the HubSpot Deals Extraction Service.

Two models:
  - ExtractionJob  : tracks an async extraction job lifecycle
  - HubSpotDeal    : a single deal record extracted from HubSpot
"""

import uuid

from django.db import models


class ExtractionJob(models.Model):
    """Represents one HubSpot deals extraction job."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    # Primary key is a UUID so job_ids are globally unique and safe to expose
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    # Pipeline metadata (mirrors DLT generator conventions)
    pipeline_name = models.CharField(max_length=100, default="hubspot_deals")
    tenant_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # We never store the real token — only a safe hint for debugging
    token_hint = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="First 8 chars + *** of the HubSpot access token",
    )

    # Timing
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)

    # Progress / results
    record_count = models.IntegerField(default=0)

    # Cursor-based checkpoint: stores the HubSpot `after` paging cursor
    last_cursor = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Last HubSpot pagination cursor (checkpoint)",
    )

    error_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["tenant_id", "status"]),
        ]

    def __str__(self) -> str:
        return f"ExtractionJob({self.id}, {self.status})"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def make_token_hint(token: str) -> str:
        """Return a safe, non-reversible token hint for logging."""
        if not token or len(token) < 4:
            return "***"
        return token[:8] + "***"

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration of the job, or None if not yet finished."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


class HubSpotDeal(models.Model):
    """
    A single HubSpot deal record extracted during an ExtractionJob.

    Field names mirror HubSpot CRM API v3 property names where possible.
    ETL metadata fields follow the DLT convention (_extracted_at, _scan_id, _tenant_id).
    """

    # Relationship to the extraction job that produced this record
    job = models.ForeignKey(
        ExtractionJob,
        on_delete=models.CASCADE,
        related_name="deals",
    )

    # HubSpot identifiers
    deal_id = models.CharField(max_length=100, db_index=True)

    # Core deal properties
    deal_name = models.CharField(max_length=500, blank=True, null=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    deal_stage = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    close_date = models.DateField(null=True, blank=True)
    pipeline = models.CharField(max_length=100, blank=True, null=True)
    owner_id = models.CharField(max_length=100, blank=True, null=True)
    create_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    deal_type = models.CharField(max_length=100, blank=True, null=True)

    # ETL metadata (DLT convention)
    extracted_at = models.DateTimeField(auto_now_add=True)
    scan_id = models.UUIDField(help_text="Mirrors the parent job UUID")
    tenant_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # Raw dump of all HubSpot properties for forward-compatibility
    raw_properties = models.JSONField(default=dict)

    class Meta:
        # A deal ID must be unique per extraction job (idempotent upsert)
        unique_together = [["job", "deal_id"]]
        ordering = ["deal_id"]
        indexes = [
            models.Index(fields=["deal_stage"]),
            models.Index(fields=["close_date"]),
            models.Index(fields=["tenant_id"]),
        ]

    def __str__(self) -> str:
        return f"HubSpotDeal(deal_id={self.deal_id}, job={self.job_id})"
