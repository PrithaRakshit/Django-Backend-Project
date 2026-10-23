"""
services/data_source.py

HubSpot Deals data source — extraction, transformation, and checkpointing.

This module mirrors the DLT (Data Load Tool) "resource" pattern:
  - A generator-based data source yields transformed records
  - Cursor-based pagination maps to HubSpot's `after` parameter
  - Checkpoints are saved to the database every N pages so that
    a cancelled/failed job can resume from where it left off

Public API:
    HubSpotDealsDataSource(access_token, job_id).extract(properties, cancel_event)
"""

import decimal
import logging
import threading
from datetime import date, datetime
from typing import Any

import django
from django.conf import settings

# Ensure Django is set up before importing models (safe to call multiple times)
django.setup() if not django.apps.registry.apps.ready else None  # noqa: B007

from api.models import ExtractionJob, HubSpotDeal  # noqa: E402
from services.hubspot_api_service import HubSpotAPIService  # noqa: E402

logger = logging.getLogger("services.data_source")


class HubSpotDealsDataSource:
    """
    Extracts HubSpot deal records and persists them to the database.

    Checkpointing:
      After every `checkpoint_every` pages the current HubSpot pagination
      cursor (`after`) is saved to `ExtractionJob.last_cursor`.  If the job
      is cancelled or the process restarts, extraction can resume from the
      last checkpoint rather than from the beginning.

    Usage:
        source = HubSpotDealsDataSource(access_token="pat-…", job_id=uuid)
        records_saved = source.extract(cancel_event=some_threading_event)
    """

    def __init__(
        self,
        access_token: str,
        job_id: Any,
        checkpoint_every: int | None = None,
    ) -> None:
        self.api_service = HubSpotAPIService(access_token)
        self.job_id = job_id
        self.checkpoint_every: int = checkpoint_every or getattr(
            settings, "CHECKPOINT_EVERY", 5
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract(
        self,
        properties: list[str] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> int:
        """
        Run the full extraction pipeline for one job.

        Fetches all deals from HubSpot, transforms them, and bulk-inserts
        into the database in page-sized batches with periodic checkpointing.

        Returns:
            Total number of deal records saved.
        """
        job = ExtractionJob.objects.get(pk=self.job_id)
        after: str | None = job.last_cursor  # Resume from checkpoint if available
        page_number = 0
        total_saved = 0

        if after:
            logger.info(
                "Resuming job %s from checkpoint cursor=%s", self.job_id, after
            )

        while True:
            if cancel_event and cancel_event.is_set():
                logger.info("Cancellation received at page %d.", page_number)
                break

            # Fetch one page of deals
            response = self.api_service.get_deals(
                limit=100, after=after, properties=properties
            )
            results: list[dict] = response.get("results", [])

            if not results:
                logger.debug("Empty page at page %d; done.", page_number)
                break

            # Transform and bulk-insert
            deal_objects = [
                self._build_deal_object(raw_deal, job)
                for raw_deal in results
            ]
            saved = self._bulk_upsert(deal_objects, job)
            total_saved += saved

            # Update in-memory record count in the DB
            ExtractionJob.objects.filter(pk=self.job_id).update(
                record_count=total_saved
            )

            page_number += 1

            # Checkpoint every N pages
            paging = response.get("paging", {})
            after = (paging.get("next") or {}).get("after")

            if page_number % self.checkpoint_every == 0 and after:
                logger.info(
                    "Checkpoint at page %d (cursor=%s, records=%d)",
                    page_number,
                    after,
                    total_saved,
                )
                ExtractionJob.objects.filter(pk=self.job_id).update(
                    last_cursor=after
                )

            if not after:
                logger.info(
                    "Extraction complete. Pages: %d, Records: %d",
                    page_number,
                    total_saved,
                )
                break

        return total_saved

    # ------------------------------------------------------------------
    # Transformation
    # ------------------------------------------------------------------

    def _build_deal_object(
        self, raw_deal: dict[str, Any], job: ExtractionJob
    ) -> HubSpotDeal:
        """
        Transform a raw HubSpot API deal dict into a HubSpotDeal instance.

        Does NOT call .save() — the caller bulk-inserts via _bulk_upsert.
        """
        props: dict[str, Any] = raw_deal.get("properties", {})

        return HubSpotDeal(
            job=job,
            deal_id=str(raw_deal["id"]),
            deal_name=_str_or_none(props.get("dealname")),
            amount=_decimal_or_none(props.get("amount")),
            deal_stage=_str_or_none(props.get("dealstage")),
            close_date=_date_or_none(props.get("closedate")),
            pipeline=_str_or_none(props.get("pipeline")),
            owner_id=_str_or_none(props.get("hubspot_owner_id")),
            create_date=_datetime_or_none(props.get("createdate")),
            last_modified_date=_datetime_or_none(props.get("hs_lastmodifieddate")),
            description=_str_or_none(props.get("description")),
            deal_type=_str_or_none(props.get("dealtype")),
            scan_id=job.id,
            tenant_id=job.tenant_id,
            raw_properties=props,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _bulk_upsert(
        deal_objects: list[HubSpotDeal], job: ExtractionJob
    ) -> int:
        """
        Bulk-insert deal records.

        Uses `ignore_conflicts=True` so re-running an extraction on the
        same job (after a resume) doesn't fail on duplicates.

        Returns the number of new records created.
        """
        if not deal_objects:
            return 0

        created = HubSpotDeal.objects.bulk_create(
            deal_objects,
            ignore_conflicts=True,
        )
        return len(created)


# ---------------------------------------------------------------------------
# Type conversion helpers
# ---------------------------------------------------------------------------

def _str_or_none(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return str(value).strip()


def _decimal_or_none(value: Any) -> decimal.Decimal | None:
    if value is None or value == "":
        return None
    try:
        return decimal.Decimal(str(value))
    except (decimal.InvalidOperation, ValueError, TypeError):
        return None


def _date_or_none(value: Any) -> date | None:
    if not value:
        return None
    try:
        # HubSpot returns ISO-8601 date strings, sometimes with time component
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        if isinstance(value, (date, datetime)):
            return value if isinstance(value, date) else value.date()
    except (ValueError, TypeError):
        pass
    return None


def _datetime_or_none(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, datetime):
            return value
    except (ValueError, TypeError):
        pass
    return None
