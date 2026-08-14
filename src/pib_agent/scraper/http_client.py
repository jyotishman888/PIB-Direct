import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pib_agent.config import get_settings

logger = logging.getLogger(__name__)


class PibFetchError(RuntimeError):
    """Raised when a PIB page cannot be fetched after retries are exhausted."""


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        headers={"User-Agent": settings.pib_request_user_agent},
        timeout=settings.pib_request_timeout_seconds,
        follow_redirects=True,
    )


def fetch_html(url: str) -> str:
    """Fetch a URL and return its response body as text, retrying on transient failures."""
    settings = get_settings()

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.pib_request_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def _do_fetch() -> str:
        with _client() as client:
            logger.debug("Fetching %s", url)
            response = client.get(url)
            response.raise_for_status()
            return response.text

    try:
        return _do_fetch()
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise PibFetchError(f"Failed to fetch {url!r} after retries: {exc}") from exc
