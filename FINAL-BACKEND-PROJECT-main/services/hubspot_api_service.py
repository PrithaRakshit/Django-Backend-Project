"""
services/hubspot_api_service.py

HubSpot CRM API v3 client for deals extraction.

Responsibilities:
  - Authenticate via Bearer token (private-app access tokens)
  - Fetch paginated deals from /crm/v3/objects/deals
  - Enforce HubSpot rate limits (150 requests / 10 seconds)
  - Validate credentials
  - Handle common API errors with meaningful exceptions
"""

import logging
import threading
import time
from collections.abc import Generator
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger("services.hubspot_api_service")


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class HubSpotAPIError(Exception):
    """Base exception for HubSpot API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HubSpotAuthError(HubSpotAPIError):
    """Raised when authentication fails (401)."""


class HubSpotRateLimitError(HubSpotAPIError):
    """Raised when rate limit is exceeded (429)."""


class HubSpotNotFoundError(HubSpotAPIError):
    """Raised when a resource is not found (404)."""


# ---------------------------------------------------------------------------
# Default deal properties to extract from HubSpot
# ---------------------------------------------------------------------------

DEFAULT_DEAL_PROPERTIES: list[str] = [
    "dealname",
    "amount",
    "dealstage",
    "closedate",
    "pipeline",
    "hubspot_owner_id",
    "createdate",
    "hs_lastmodifieddate",
    "description",
    "dealtype",
    "hs_deal_stage_probability",
    "num_associated_contacts",
    "hs_is_closed",
    "hs_is_closed_won",
]


# ---------------------------------------------------------------------------
# Rate limiter (token bucket, thread-safe)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """
    Simple sliding-window rate limiter.

    Tracks request timestamps and sleeps when the allowed count
    within the period window would be exceeded.
    """

    def __init__(self, max_requests: int, period_seconds: int) -> None:
        self._max = max_requests
        self._period = period_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until a request slot is available."""
        with self._lock:
            now = time.monotonic()
            # Drop timestamps outside the current window
            self._timestamps = [
                t for t in self._timestamps if now - t < self._period
            ]
            if len(self._timestamps) >= self._max:
                oldest = self._timestamps[0]
                sleep_for = self._period - (now - oldest) + 0.01
                if sleep_for > 0:
                    logger.debug(
                        "Rate limit reached; sleeping %.2fs", sleep_for
                    )
                    time.sleep(sleep_for)
                # Re-clean after sleeping
                now = time.monotonic()
                self._timestamps = [
                    t for t in self._timestamps if now - t < self._period
                ]
            self._timestamps.append(time.monotonic())


# ---------------------------------------------------------------------------
# HubSpot API Service
# ---------------------------------------------------------------------------

class HubSpotAPIService:
    """
    Thin HTTP client wrapping the HubSpot CRM API v3.

    Usage:
        svc = HubSpotAPIService(access_token="pat-na1-...")
        svc.validate_credentials()
        for deal in svc.get_all_deals():
            print(deal)
    """

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token
        self.base_url: str = getattr(settings, "HUBSPOT_BASE_URL", "https://api.hubapi.com")
        self.timeout: int = getattr(settings, "HUBSPOT_TIMEOUT", 30)

        rate_limit_reqs = getattr(settings, "HUBSPOT_RATE_LIMIT_REQUESTS", 150)
        rate_limit_period = getattr(settings, "HUBSPOT_RATE_LIMIT_PERIOD", 10)
        self._limiter = _RateLimiter(rate_limit_reqs, rate_limit_period)

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def validate_credentials(self) -> bool:
        """
        Validate the access token by fetching a single deal.

        Returns True if the token is valid.
        Raises HubSpotAuthError if the token is rejected.
        Raises HubSpotAPIError for other failure modes.
        """
        logger.info("Validating HubSpot credentials …")
        try:
            self.get_deals(limit=1, properties=["dealname"])
            logger.info("Credentials valid.")
            return True
        except HubSpotAuthError:
            raise
        except HubSpotAPIError:
            raise

    def get_deals(
        self,
        limit: int = 100,
        after: str | None = None,
        properties: list[str] | None = None,
        archived: bool = False,
    ) -> dict[str, Any]:
        """
        Fetch one page of deals from HubSpot CRM API v3.

        Args:
            limit:      Maximum number of deals per page (1–100).
            after:      Cursor for the next page (from previous response).
            properties: Deal property names to include in the response.
            archived:   Whether to include archived deals.

        Returns:
            Raw API response dict with keys: ``results``, ``paging``.
        """
        if properties is None:
            properties = DEFAULT_DEAL_PROPERTIES

        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "archived": str(archived).lower(),
            "properties": ",".join(properties),
        }
        if after:
            params["after"] = after

        return self._get("/crm/v3/objects/deals", params=params)

    def get_all_deals(
        self,
        properties: list[str] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """
        Generator that yields every deal from HubSpot, handling pagination.

        Each yielded item is the raw HubSpot deal dict:
          {
            "id": "12345",
            "properties": { "dealname": "...", "amount": "...", ... },
            "createdAt": "...",
            "updatedAt": "...",
            "archived": false
          }

        Args:
            properties:   Property names to fetch (defaults to DEFAULT_DEAL_PROPERTIES).
            cancel_event: If set and signalled, iteration stops cleanly.
        """
        after: str | None = None
        page = 0

        while True:
            if cancel_event and cancel_event.is_set():
                logger.info("Cancellation signal received; stopping pagination.")
                break

            logger.debug("Fetching deals page %d (after=%s)", page + 1, after)
            response = self.get_deals(limit=100, after=after, properties=properties)

            results: list[dict] = response.get("results", [])
            for deal in results:
                yield deal

            page += 1

            # Follow the paging cursor if present
            paging = response.get("paging", {})
            next_page = paging.get("next", {})
            after = next_page.get("after")

            if not after:
                logger.info(
                    "All deals fetched. Total pages: %d", page
                )
                break

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """Make a rate-limited GET request and return the parsed JSON body."""
        self._limiter.acquire()
        url = f"{self.base_url}{path}"
        logger.debug("GET %s params=%s", url, params)

        try:
            response = self._session.get(url, params=params, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            raise HubSpotAPIError(
                f"Request timed out after {self.timeout}s: {exc}"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise HubSpotAPIError(f"Connection error: {exc}") from exc

        self._handle_response_error(response)
        return response.json()

    @staticmethod
    def _handle_response_error(response: requests.Response) -> None:
        """Raise an appropriate exception for non-2xx responses."""
        if response.status_code == 200:
            return

        try:
            error_body = response.json()
            message = error_body.get("message", response.text)
        except Exception:
            message = response.text

        if response.status_code == 401:
            raise HubSpotAuthError(
                f"Authentication failed: {message}", status_code=401
            )
        if response.status_code == 403:
            raise HubSpotAuthError(
                f"Forbidden — check token scopes (crm.objects.deals.read required): {message}",
                status_code=403,
            )
        if response.status_code == 404:
            raise HubSpotNotFoundError(f"Resource not found: {message}", status_code=404)
        if response.status_code == 429:
            raise HubSpotRateLimitError(
                f"Rate limit exceeded: {message}", status_code=429
            )
        raise HubSpotAPIError(
            f"HubSpot API error {response.status_code}: {message}",
            status_code=response.status_code,
        )
