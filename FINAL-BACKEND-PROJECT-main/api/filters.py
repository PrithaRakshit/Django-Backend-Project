"""
django-filter FilterSet classes for the HubSpot Deals Extraction Service.
"""

import django_filters

from api.models import ExtractionJob, HubSpotDeal


class ExtractionJobFilter(django_filters.FilterSet):
    """Filters for the job list endpoint."""

    status = django_filters.CharFilter(field_name="status", lookup_expr="iexact")
    pipeline_name = django_filters.CharFilter(
        field_name="pipeline_name", lookup_expr="iexact"
    )
    tenant_id = django_filters.CharFilter(
        field_name="tenant_id", lookup_expr="iexact"
    )
    created_after = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )

    class Meta:
        model = ExtractionJob
        fields = ["status", "pipeline_name", "tenant_id"]


class HubSpotDealFilter(django_filters.FilterSet):
    """Filters for the deal results endpoint."""

    deal_stage = django_filters.CharFilter(
        field_name="deal_stage", lookup_expr="iexact"
    )
    min_amount = django_filters.NumberFilter(field_name="amount", lookup_expr="gte")
    max_amount = django_filters.NumberFilter(field_name="amount", lookup_expr="lte")
    close_date_after = django_filters.DateFilter(
        field_name="close_date", lookup_expr="gte"
    )
    close_date_before = django_filters.DateFilter(
        field_name="close_date", lookup_expr="lte"
    )

    class Meta:
        model = HubSpotDeal
        fields = ["deal_stage", "deal_type", "pipeline", "owner_id"]
