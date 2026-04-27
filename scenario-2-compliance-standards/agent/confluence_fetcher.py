"""
Confluence Standards Fetcher — Scenario 2.

Pulls engineering standards and technical documentation from Confluence
and assembles them into a structured context for the AI PR reviewer.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from shared.utils import truncate

logger = logging.getLogger(__name__)


@dataclass
class StandardsDocument:
    """A Confluence page representing an engineering standard or policy."""

    page_id: str
    title: str
    space_key: str
    url: str
    content: str
    last_modified: str = ""
    labels: list[str] = field(default_factory=list)


class ConfluenceFetcher:
    """
    Fetches engineering standards and technical documentation from Confluence.

    Supports both Confluence Cloud (atlassian.net) and Confluence Data Center.
    Authentication uses HTTP Basic auth with an API token.
    """

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
    ) -> None:
        self.base_url = (url or os.environ.get("CONFLUENCE_URL", "")).rstrip("/")
        self.username = username or os.environ.get("CONFLUENCE_USERNAME", "")
        self.api_token = api_token or os.environ.get("CONFLUENCE_API_TOKEN", "")

        if not self.base_url:
            raise EnvironmentError("CONFLUENCE_URL is not set.")
        if not self.username:
            raise EnvironmentError("CONFLUENCE_USERNAME is not set.")
        if not self.api_token:
            raise EnvironmentError("CONFLUENCE_API_TOKEN is not set.")

        self._session = requests.Session()
        self._session.auth = (self.username, self.api_token)
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session.mount("http://", HTTPAdapter(max_retries=retry))

        logger.info("ConfluenceFetcher initialised (url=%s)", self.base_url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _api(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/rest/api/{path}"
        resp = self._session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _strip_html(html: str) -> str:
        """Strip HTML tags and decode common entities."""
        text = re.sub(r"<[^>]+>", " ", html)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&nbsp;", " ").replace("&quot;", '"')
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_space_pages(
        self,
        space_key: str,
        max_pages: int = 50,
    ) -> list[StandardsDocument]:
        """
        Fetch all pages from a Confluence space.

        Args:
            space_key: The Confluence space key (e.g. 'ENG', 'DEVOPS').
            max_pages: Maximum number of pages to retrieve.

        Returns:
            List of :class:`StandardsDocument` objects.
        """
        logger.info("Fetching pages from Confluence space '%s'", space_key)
        results = self._api(
            "content",
            params={
                "spaceKey": space_key,
                "type": "page",
                "expand": "body.storage,version,metadata.labels",
                "limit": max_pages,
            },
        )

        documents: list[StandardsDocument] = []
        for page in results.get("results", []):
            doc = self._page_to_document(page, space_key)
            documents.append(doc)

        logger.info("Fetched %d documents from space '%s'", len(documents), space_key)
        return documents

    def fetch_page_by_id(self, page_id: str) -> StandardsDocument:
        """Fetch a single Confluence page by its numeric ID."""
        logger.info("Fetching Confluence page id=%s", page_id)
        page = self._api(
            f"content/{page_id}",
            params={"expand": "body.storage,version,metadata.labels"},
        )
        space_key = page.get("space", {}).get("key", "")
        return self._page_to_document(page, space_key)

    def fetch_all_standards(
        self,
        space_keys: list[str] | None = None,
        extra_page_ids: list[str] | None = None,
    ) -> list[StandardsDocument]:
        """
        Fetch all standards from configured spaces and/or specific pages.

        Args:
            space_keys: List of space keys. Falls back to CONFLUENCE_SPACE_KEYS env var.
            extra_page_ids: Additional page IDs to always include.
                            Falls back to CONFLUENCE_STANDARDS_PAGE_IDS env var.

        Returns:
            De-duplicated list of :class:`StandardsDocument` objects.
        """
        if space_keys is None:
            raw = os.environ.get("CONFLUENCE_SPACE_KEYS", "")
            space_keys = [k.strip() for k in raw.split(",") if k.strip()]

        if extra_page_ids is None:
            raw = os.environ.get("CONFLUENCE_STANDARDS_PAGE_IDS", "")
            extra_page_ids = [p.strip() for p in raw.split(",") if p.strip()]

        seen_ids: set[str] = set()
        documents: list[StandardsDocument] = []

        for key in space_keys:
            for doc in self.fetch_space_pages(key):
                if doc.page_id not in seen_ids:
                    seen_ids.add(doc.page_id)
                    documents.append(doc)

        for page_id in extra_page_ids:
            if page_id not in seen_ids:
                try:
                    doc = self.fetch_page_by_id(page_id)
                    seen_ids.add(doc.page_id)
                    documents.append(doc)
                except Exception:
                    logger.exception("Failed to fetch extra page id=%s", page_id)

        logger.info("Total standards documents fetched: %d", len(documents))
        return documents

    def _page_to_document(self, page: dict, space_key: str) -> StandardsDocument:
        body_html = page.get("body", {}).get("storage", {}).get("value", "")
        plain_text = self._strip_html(body_html)
        labels = [
            label["name"]
            for label in page.get("metadata", {}).get("labels", {}).get("results", [])
        ]
        page_url = f"{self.base_url}/wiki/spaces/{space_key}/pages/{page['id']}"

        return StandardsDocument(
            page_id=str(page["id"]),
            title=page.get("title", "Untitled"),
            space_key=space_key,
            url=page_url,
            content=plain_text,
            last_modified=page.get("version", {}).get("when", ""),
            labels=labels,
        )
