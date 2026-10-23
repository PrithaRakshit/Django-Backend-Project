"""
Custom pagination classes for the HubSpot Deals Extraction Service.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Default pagination: 20 items per page, max 100.
    Clients can override with ?page_size=N.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page": self.page.number,
                "total_pages": self.page.paginator.num_pages,
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "page": {"type": "integer"},
                "total_pages": {"type": "integer"},
                "results": schema,
            },
        }
