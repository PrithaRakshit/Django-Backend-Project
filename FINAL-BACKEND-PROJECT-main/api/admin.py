"""
api/admin.py — Django admin registration for inspecting data.
"""

from django.contrib import admin

from api.models import ExtractionJob, HubSpotDeal


@admin.register(ExtractionJob)
class ExtractionJobAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "status",
        "pipeline_name",
        "tenant_id",
        "record_count",
        "start_time",
        "end_time",
        "created_at",
    ]
    list_filter = ["status", "pipeline_name"]
    search_fields = ["id", "tenant_id", "token_hint"]
    readonly_fields = ["id", "token_hint", "created_at", "updated_at"]
    ordering = ["-created_at"]


@admin.register(HubSpotDeal)
class HubSpotDealAdmin(admin.ModelAdmin):
    list_display = [
        "deal_id",
        "deal_name",
        "amount",
        "deal_stage",
        "close_date",
        "job",
        "extracted_at",
    ]
    list_filter = ["deal_stage", "deal_type", "pipeline"]
    search_fields = ["deal_id", "deal_name", "description"]
    readonly_fields = ["extracted_at", "scan_id"]
    ordering = ["deal_id"]
