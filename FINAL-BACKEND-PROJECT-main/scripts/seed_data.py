"""
scripts/seed_data.py

Seeds sample extraction jobs and deal records for manual testing.
Run with: python scripts/seed_data.py

Requires the virtual environment to be active and migrations to be applied.
"""

import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.utils import timezone

from api.models import ExtractionJob, HubSpotDeal


def seed():
    print("Seeding sample data …")

    # Clean up existing seed data (optional)
    ExtractionJob.objects.filter(pipeline_name="hubspot_deals_seed").delete()

    # Create a completed job
    job = ExtractionJob.objects.create(
        status="completed",
        pipeline_name="hubspot_deals_seed",
        token_hint="pat-na1-***",
        tenant_id="demo-tenant",
        start_time=timezone.now(),
        end_time=timezone.now(),
        record_count=5,
    )

    # 5 test deals matching the assessment requirement
    deals = [
        {
            "deal_id": "seed-001",
            "deal_name": "Startup Seed Round",
            "amount": "5000.00",
            "deal_stage": "qualifiedtobuy",
            "pipeline": "default",
            "deal_type": "newbusiness",
        },
        {
            "deal_id": "seed-002",
            "deal_name": "SMB Annual License",
            "amount": "25000.00",
            "deal_stage": "presentationscheduled",
            "pipeline": "default",
            "deal_type": "newbusiness",
        },
        {
            "deal_id": "seed-003",
            "deal_name": "Enterprise Platform",
            "amount": "50000.00",
            "deal_stage": "closedwon",
            "pipeline": "default",
            "deal_type": "existingbusiness",
        },
        {
            "deal_id": "seed-004",
            "deal_name": "Competitor Switchover",
            "amount": "75000.00",
            "deal_stage": "closedlost",
            "pipeline": "default",
            "deal_type": "newbusiness",
        },
        {
            "deal_id": "seed-005",
            "deal_name": "Fortune 500 Contract",
            "amount": "100000.00",
            "deal_stage": "qualifiedtobuy",
            "pipeline": "enterprise",
            "deal_type": "newbusiness",
        },
    ]

    for d in deals:
        HubSpotDeal.objects.create(
            job=job,
            scan_id=job.id,
            tenant_id=job.tenant_id,
            raw_properties=d,
            **d,
        )
        print(f"  Created deal: {d['deal_name']} ({d['deal_stage']}, ${d['amount']})")

    # Create a pending job
    ExtractionJob.objects.create(
        status="pending",
        pipeline_name="hubspot_deals_seed",
        token_hint="pat-na1-***",
        tenant_id="demo-tenant",
    )

    # Create a failed job
    ExtractionJob.objects.create(
        status="failed",
        pipeline_name="hubspot_deals_seed",
        token_hint="pat-na1-***",
        start_time=timezone.now(),
        end_time=timezone.now(),
        error_message="Authentication failed: Invalid access token.",
    )

    print(f"\nSeeded 1 completed job (5 deals), 1 pending job, 1 failed job.")
    print(f"Completed job ID: {job.id}")
    print("\nYou can now test:")
    print(f"  GET /api/v1/scan/status/{job.id}")
    print(f"  GET /api/v1/scan/result/{job.id}")


if __name__ == "__main__":
    seed()
