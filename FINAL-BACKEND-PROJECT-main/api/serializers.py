"""
DRF serializers for the HubSpot Deals Extraction Service.
"""

from rest_framework import serializers

from api.models import ExtractionJob, HubSpotDeal


# ---------------------------------------------------------------------------
# HubSpot Deal serializer
# ---------------------------------------------------------------------------

class HubSpotDealSerializer(serializers.ModelSerializer):
    """Read-only serializer for extracted deal records."""

    class Meta:
        model = HubSpotDeal
        fields = [
            "id",
            "deal_id",
            "deal_name",
            "amount",
            "deal_stage",
            "close_date",
            "pipeline",
            "owner_id",
            "create_date",
            "last_modified_date",
            "description",
            "deal_type",
            "extracted_at",
            "scan_id",
            "tenant_id",
            "raw_properties",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Extraction Job serializers
# ---------------------------------------------------------------------------

class ExtractionJobSerializer(serializers.ModelSerializer):
    """Full serializer for listing and detail views."""

    duration_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = ExtractionJob
        fields = [
            "id",
            "status",
            "pipeline_name",
            "tenant_id",
            "token_hint",
            "start_time",
            "end_time",
            "record_count",
            "last_cursor",
            "error_message",
            "duration_seconds",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ExtractionJobStatusSerializer(serializers.ModelSerializer):
    """Slim serializer returned by the /status/ endpoint."""

    duration_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = ExtractionJob
        fields = [
            "id",
            "status",
            "record_count",
            "start_time",
            "end_time",
            "pipeline_name",
            "error_message",
            "duration_seconds",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Request serializers (for Swagger / input validation)
# ---------------------------------------------------------------------------

class StartScanRequestSerializer(serializers.Serializer):
    """
    Request body for POST /api/v1/scan/start.

    The access_token is used only within the request lifecycle;
    only a safe hint is persisted to the database.
    """

    access_token = serializers.CharField(
        required=True,
        min_length=10,
        help_text="HubSpot private-app access token (pat-na1-... or similar).",
    )
    properties = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        help_text=(
            "Optional list of HubSpot deal property names to extract. "
            "Defaults to the standard set if omitted."
        ),
    )
    tenant_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default=None,
        help_text="Optional tenant identifier for multi-tenant deployments.",
    )


class StartScanResponseSerializer(serializers.Serializer):
    """Response schema for a successful POST /api/v1/scan/start."""

    job_id = serializers.UUIDField()
    status = serializers.CharField()
    message = serializers.CharField()


class CancelJobResponseSerializer(serializers.Serializer):
    """Response for POST /api/v1/scan/cancel/<job_id>."""

    job_id = serializers.UUIDField()
    status = serializers.CharField()
    message = serializers.CharField()


class StatisticsSerializer(serializers.Serializer):
    """Response for GET /api/v1/jobs/statistics."""

    total_jobs = serializers.IntegerField()
    pending_jobs = serializers.IntegerField()
    running_jobs = serializers.IntegerField()
    completed_jobs = serializers.IntegerField()
    failed_jobs = serializers.IntegerField()
    cancelled_jobs = serializers.IntegerField()
    total_records_extracted = serializers.IntegerField()
    avg_extraction_time_seconds = serializers.FloatField(allow_null=True)


class HealthSerializer(serializers.Serializer):
    """Response for GET /api/v1/health."""

    status = serializers.CharField()
    service = serializers.CharField()
    version = serializers.CharField()
