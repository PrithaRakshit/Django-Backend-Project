"""
api/views.py

All API views for the HubSpot Deals Extraction Service.

Endpoints implemented:
  GET  /api/v1/health                    → HealthCheckView
  POST /api/v1/scan/start                → StartScanView
  GET  /api/v1/scan/status/<job_id>      → ScanStatusView
  GET  /api/v1/scan/result/<job_id>      → ScanResultView
  POST /api/v1/scan/cancel/<job_id>      → CancelScanView
  DEL  /api/v1/scan/remove/<job_id>      → RemoveScanView
  GET  /api/v1/jobs/jobs                 → JobListView
  GET  /api/v1/jobs/statistics           → JobStatisticsView
"""

import logging

from django.db.models import Avg, ExpressionWrapper, F, FloatField, Sum
from django.db.models.functions import Extract
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import filters, generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.filters import ExtractionJobFilter, HubSpotDealFilter
from api.models import ExtractionJob, HubSpotDeal
from api.pagination import StandardResultsSetPagination
from api.serializers import (
    CancelJobResponseSerializer,
    ExtractionJobSerializer,
    ExtractionJobStatusSerializer,
    HealthSerializer,
    HubSpotDealSerializer,
    StartScanRequestSerializer,
    StartScanResponseSerializer,
    StatisticsSerializer,
)
from services.extraction_service import extraction_service

logger = logging.getLogger("api.views")


# ---------------------------------------------------------------------------
# 1. Health Check
# ---------------------------------------------------------------------------

class HealthCheckView(APIView):
    """
    GET /api/v1/health

    Returns service health status. Always 200 when the service is running.
    Used by Docker health checks and monitoring systems.
    """

    permission_classes = []
    authentication_classes = []

    @extend_schema(
        tags=["Health"],
        summary="Service health check",
        responses={200: HealthSerializer},
    )
    def get(self, request: Request) -> Response:
        data = {
            "status": "ok",
            "service": "hubspot_deals",
            "version": "1.0.0",
        }
        return Response(data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 2. Start Scan
# ---------------------------------------------------------------------------

class StartScanView(APIView):
    """
    POST /api/v1/scan/start

    Accepts a HubSpot private-app access token and starts an async
    background extraction job.  Returns 202 Accepted immediately with
    a job_id that can be polled via /api/v1/scan/status/<job_id>.
    """

    permission_classes = []
    authentication_classes = []

    @extend_schema(
        tags=["Scan"],
        summary="Start a new HubSpot deals extraction",
        request=StartScanRequestSerializer,
        responses={
            202: StartScanResponseSerializer,
            400: OpenApiResponse(description="Validation error — missing or invalid fields"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = StartScanRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        access_token: str = data["access_token"]
        properties: list[str] = data.get("properties") or []
        tenant_id: str | None = data.get("tenant_id")

        # Create the job record
        job = ExtractionJob.objects.create(
            status=ExtractionJob.Status.PENDING,
            token_hint=ExtractionJob.make_token_hint(access_token),
            tenant_id=tenant_id or None,
        )

        # Launch background extraction
        extraction_service.start_extraction(
            job_id=job.id,
            access_token=access_token,
            properties=properties if properties else None,
        )

        logger.info("Started extraction job %s for tenant=%s", job.id, tenant_id)

        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
                "message": "Extraction job started. Poll /api/v1/scan/status/<job_id> for progress.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# 3. Scan Status
# ---------------------------------------------------------------------------

class ScanStatusView(APIView):
    """
    GET /api/v1/scan/status/<job_id>

    Returns the current status, timing, and record count for a job.
    Clients should poll this endpoint until status is 'completed' or 'failed'.
    """

    permission_classes = []
    authentication_classes = []

    @extend_schema(
        tags=["Scan"],
        summary="Get extraction job status",
        responses={
            200: ExtractionJobStatusSerializer,
            404: OpenApiResponse(description="Job not found"),
        },
    )
    def get(self, request: Request, job_id: str) -> Response:
        try:
            job = ExtractionJob.objects.get(pk=job_id)
        except (ExtractionJob.DoesNotExist, Exception):
            return Response(
                {"error": f"Job '{job_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ExtractionJobStatusSerializer(job)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 4. Scan Result
# ---------------------------------------------------------------------------

class ScanResultView(generics.ListAPIView):
    """
    GET /api/v1/scan/result/<job_id>

    Returns paginated deal records extracted by a completed job.
    Supports filtering by deal_stage, amount range, close_date range.
    Only available when the job status is 'completed'.
    """

    permission_classes = []
    authentication_classes = []
    serializer_class = HubSpotDealSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    ordering_fields = ["deal_id", "amount", "close_date", "deal_stage", "extracted_at"]
    ordering = ["deal_id"]
    search_fields = ["deal_name", "deal_stage", "deal_type", "description"]

    @extend_schema(
        tags=["Scan"],
        summary="Retrieve paginated deal records for a completed job",
        parameters=[
            OpenApiParameter("job_id", str, OpenApiParameter.PATH, description="UUID of the extraction job"),
            OpenApiParameter("deal_stage", str, description="Filter by deal stage"),
            OpenApiParameter("min_amount", float, description="Minimum deal amount"),
            OpenApiParameter("max_amount", float, description="Maximum deal amount"),
            OpenApiParameter("search", str, description="Search deal_name, deal_stage, description"),
            OpenApiParameter("ordering", str, description="Field to sort by (prefix - for descending)"),
            OpenApiParameter("page", int, description="Page number"),
            OpenApiParameter("page_size", int, description="Results per page (max 100)"),
        ],
        responses={
            200: HubSpotDealSerializer(many=True),
            404: OpenApiResponse(description="Job not found"),
            409: OpenApiResponse(description="Job is not yet completed"),
        },
    )
    def get(self, request: Request, job_id: str, *args, **kwargs) -> Response:
        try:
            job = ExtractionJob.objects.get(pk=job_id)
        except (ExtractionJob.DoesNotExist, Exception):
            return Response(
                {"error": f"Job '{job_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if job.status != ExtractionJob.Status.COMPLETED:
            return Response(
                {
                    "error": f"Results are only available for completed jobs. "
                             f"Current status: '{job.status}'."
                },
                status=status.HTTP_409_CONFLICT,
            )

        self._job = job
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return HubSpotDeal.objects.filter(job=self._job).select_related("job")


# ---------------------------------------------------------------------------
# 5. Cancel Scan
# ---------------------------------------------------------------------------

class CancelScanView(APIView):
    """
    POST /api/v1/scan/cancel/<job_id>

    Cancels a pending or running extraction job.
    Completed, failed, or already-cancelled jobs cannot be cancelled.
    """

    permission_classes = []
    authentication_classes = []
    serializer_class = CancelJobResponseSerializer  # for drf-spectacular introspection

    @extend_schema(
        tags=["Scan"],
        summary="Cancel a pending or running extraction job",
        responses={
            200: CancelJobResponseSerializer,
            404: OpenApiResponse(description="Job not found"),
            409: OpenApiResponse(description="Job cannot be cancelled in its current state"),
        },
    )
    def post(self, request: Request, job_id: str) -> Response:
        try:
            job = ExtractionJob.objects.get(pk=job_id)
        except (ExtractionJob.DoesNotExist, Exception):
            return Response(
                {"error": f"Job '{job_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if job.status not in (
            ExtractionJob.Status.PENDING,
            ExtractionJob.Status.RUNNING,
        ):
            return Response(
                {
                    "error": f"Cannot cancel a job with status '{job.status}'. "
                             f"Only 'pending' and 'running' jobs can be cancelled."
                },
                status=status.HTTP_409_CONFLICT,
            )

        extraction_service.cancel_extraction(job_id=job.id)

        # Refresh from DB to get the updated status
        job.refresh_from_db()

        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
                "message": "Job cancelled successfully.",
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# 6. Remove Scan
# ---------------------------------------------------------------------------

class RemoveScanView(APIView):
    """
    DELETE /api/v1/scan/remove/<job_id>

    Permanently deletes an extraction job and all its associated deal records.
    After deletion, any subsequent GET to /status/ or /result/ will return 404.
    """

    permission_classes = []
    authentication_classes = []

    @extend_schema(
        tags=["Scan"],
        summary="Delete an extraction job and all its deal data",
        responses={
            204: OpenApiResponse(description="Job and data deleted successfully"),
            404: OpenApiResponse(description="Job not found"),
        },
    )
    def delete(self, request: Request, job_id: str) -> Response:
        try:
            job = ExtractionJob.objects.get(pk=job_id)
        except (ExtractionJob.DoesNotExist, Exception):
            return Response(
                {"error": f"Job '{job_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        job.delete()  # Cascades to HubSpotDeal via FK

        logger.info("Deleted job %s and its deal data.", job_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# 7. Job List
# ---------------------------------------------------------------------------

class JobListView(generics.ListAPIView):
    """
    GET /api/v1/jobs/jobs

    Returns a paginated list of all extraction jobs.
    Supports filtering by status, pipeline_name, tenant_id, and date range.
    Supports ordering by created_at, updated_at, record_count.
    """

    permission_classes = []
    authentication_classes = []
    serializer_class = ExtractionJobSerializer
    pagination_class = StandardResultsSetPagination
    filterset_class = ExtractionJobFilter
    filter_backends = [
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    ordering_fields = ["created_at", "updated_at", "record_count", "status"]
    ordering = ["-created_at"]
    search_fields = ["pipeline_name", "tenant_id", "status"]

    @extend_schema(
        tags=["Jobs"],
        summary="List all extraction jobs",
        parameters=[
            OpenApiParameter("status", str, description="Filter by status (pending/running/completed/failed/cancelled)"),
            OpenApiParameter("pipeline_name", str, description="Filter by pipeline name"),
            OpenApiParameter("tenant_id", str, description="Filter by tenant ID"),
            OpenApiParameter("created_after", str, description="ISO-8601 datetime — only jobs created after"),
            OpenApiParameter("created_before", str, description="ISO-8601 datetime — only jobs created before"),
            OpenApiParameter("ordering", str, description="Field to sort by"),
            OpenApiParameter("page", int, description="Page number"),
            OpenApiParameter("page_size", int, description="Results per page (max 100)"),
        ],
        responses={200: ExtractionJobSerializer(many=True)},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = ExtractionJob.objects.all()

        # Manual filter support for non-filterset params
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status__iexact=status_param)

        pipeline = self.request.query_params.get("pipeline_name")
        if pipeline:
            qs = qs.filter(pipeline_name__iexact=pipeline)

        tenant = self.request.query_params.get("tenant_id")
        if tenant:
            qs = qs.filter(tenant_id__iexact=tenant)

        created_after = self.request.query_params.get("created_after")
        if created_after:
            qs = qs.filter(created_at__gte=created_after)

        created_before = self.request.query_params.get("created_before")
        if created_before:
            qs = qs.filter(created_at__lte=created_before)

        return qs


# ---------------------------------------------------------------------------
# 8. Job Statistics
# ---------------------------------------------------------------------------

class JobStatisticsView(APIView):
    """
    GET /api/v1/jobs/statistics

    Returns aggregated metrics for all extraction jobs:
    counts by status, total records extracted, and average extraction time.
    """

    permission_classes = []
    authentication_classes = []

    @extend_schema(
        tags=["Jobs"],
        summary="Get aggregated job statistics",
        responses={200: StatisticsSerializer},
    )
    def get(self, request: Request) -> Response:
        qs = ExtractionJob.objects.all()

        total_jobs = qs.count()
        pending_jobs = qs.filter(status="pending").count()
        running_jobs = qs.filter(status="running").count()
        completed_jobs = qs.filter(status="completed").count()
        failed_jobs = qs.filter(status="failed").count()
        cancelled_jobs = qs.filter(status="cancelled").count()

        total_records = (
            qs.filter(status="completed").aggregate(total=Sum("record_count"))["total"]
            or 0
        )

        # Average extraction time (seconds) for completed jobs
        completed_qs = qs.filter(
            status="completed",
            start_time__isnull=False,
            end_time__isnull=False,
        )
        avg_time: float | None = None
        if completed_qs.exists():
            durations = [
                (j.end_time - j.start_time).total_seconds()
                for j in completed_qs
                if j.end_time and j.start_time
            ]
            if durations:
                avg_time = sum(durations) / len(durations)

        data = {
            "total_jobs": total_jobs,
            "pending_jobs": pending_jobs,
            "running_jobs": running_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "cancelled_jobs": cancelled_jobs,
            "total_records_extracted": total_records,
            "avg_extraction_time_seconds": avg_time,
        }

        return Response(data, status=status.HTTP_200_OK)
