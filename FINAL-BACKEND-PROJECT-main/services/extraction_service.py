"""
services/extraction_service.py

Orchestrates background HubSpot extraction jobs.

Each extraction runs in a daemon thread so the API view returns immediately
with 202 Accepted.  Cancellation is implemented with threading.Event:
the running data source checks the event and stops cleanly.

Thread safety:
  _running_jobs is a module-level dict protected by _lock.
  All mutations to ExtractionJob records are made through
  QuerySet.update() to minimise race conditions.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("services.extraction_service")

# ---------------------------------------------------------------------------
# Module-level state (kept per-process; not shared across workers)
# ---------------------------------------------------------------------------

# Maps job_id (str) → threading.Event used to signal cancellation
_running_jobs: dict[str, threading.Event] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ExtractionService:
    """Manages the lifecycle of background extraction jobs."""

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def start_extraction(
        self,
        job_id: Any,
        access_token: str,
        properties: list[str] | None = None,
    ) -> None:
        """
        Launch a background thread that runs the full extraction pipeline.

        The job's status must already be set to 'pending' by the caller
        before invoking this method.

        Args:
            job_id:       UUID of the ExtractionJob record.
            access_token: HubSpot private-app access token.
            properties:   Optional list of deal property names to fetch.
        """
        cancel_event = threading.Event()
        job_key = str(job_id)

        with _lock:
            _running_jobs[job_key] = cancel_event

        thread = threading.Thread(
            target=self._run_extraction,
            args=(job_key, access_token, properties, cancel_event),
            daemon=True,
            name=f"extraction-{job_key[:8]}",
        )
        thread.start()
        logger.info("Started extraction thread for job %s", job_key)

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel_extraction(self, job_id: Any) -> bool:
        """
        Signal a running or pending job to cancel.

        Returns True if a cancel signal was sent, False if the job was
        not found in the running-jobs registry (already finished/removed).
        """
        # Import here to avoid circular imports at module load time
        from api.models import ExtractionJob

        job_key = str(job_id)

        with _lock:
            event = _running_jobs.get(job_key)

        if event:
            event.set()
            logger.info("Cancel signal sent to job %s", job_key)

        # Regardless of thread state, mark the DB record as cancelled
        now = datetime.now(timezone.utc)
        updated = ExtractionJob.objects.filter(
            pk=job_id, status__in=["pending", "running"]
        ).update(status="cancelled", end_time=now)

        with _lock:
            _running_jobs.pop(job_key, None)

        return updated > 0

    # ------------------------------------------------------------------
    # Background thread target
    # ------------------------------------------------------------------

    def _run_extraction(
        self,
        job_key: str,
        access_token: str,
        properties: list[str] | None,
        cancel_event: threading.Event,
    ) -> None:
        """
        Background thread: validate credentials, run extraction, update job status.
        """
        # Delayed imports so this module can be imported without Django being ready
        from api.models import ExtractionJob
        from services.data_source import HubSpotDealsDataSource
        from services.hubspot_api_service import HubSpotAPIError, HubSpotAuthError

        now = datetime.now(timezone.utc)

        try:
            # Mark job as running
            ExtractionJob.objects.filter(pk=job_key).update(
                status="running", start_time=now
            )
            logger.info("Job %s is now running.", job_key)

            if cancel_event.is_set():
                self._mark_cancelled(job_key)
                return

            # Validate credentials before starting real extraction
            from services.hubspot_api_service import HubSpotAPIService

            svc = HubSpotAPIService(access_token)
            svc.validate_credentials()

            # Run the extraction pipeline
            source = HubSpotDealsDataSource(
                access_token=access_token,
                job_id=job_key,
            )
            total = source.extract(
                properties=properties,
                cancel_event=cancel_event,
            )

            if cancel_event.is_set():
                self._mark_cancelled(job_key)
            else:
                end = datetime.now(timezone.utc)
                ExtractionJob.objects.filter(pk=job_key).update(
                    status="completed",
                    end_time=end,
                    record_count=total,
                    last_cursor=None,  # Clear checkpoint on success
                )
                logger.info("Job %s completed. Records extracted: %d", job_key, total)

        except HubSpotAuthError as exc:
            logger.error("Job %s failed — auth error: %s", job_key, exc)
            self._mark_failed(job_key, str(exc))

        except HubSpotAPIError as exc:
            logger.error("Job %s failed — HubSpot API error: %s", job_key, exc)
            self._mark_failed(job_key, str(exc))

        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed — unexpected error: %s", job_key, exc)
            self._mark_failed(job_key, f"Unexpected error: {exc}")

        finally:
            with _lock:
                _running_jobs.pop(job_key, None)

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mark_cancelled(job_key: str) -> None:
        from api.models import ExtractionJob

        now = datetime.now(timezone.utc)
        ExtractionJob.objects.filter(pk=job_key).update(
            status="cancelled", end_time=now
        )
        logger.info("Job %s marked as cancelled.", job_key)

    @staticmethod
    def _mark_failed(job_key: str, error_message: str) -> None:
        from api.models import ExtractionJob

        now = datetime.now(timezone.utc)
        ExtractionJob.objects.filter(pk=job_key).update(
            status="failed",
            end_time=now,
            error_message=error_message,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

extraction_service = ExtractionService()
