"""
Build Failure Fetcher — Scenario 1.

Retrieves failed Azure DevOps pipeline runs and enriches them with
per-task error details, ready for downstream pattern mining.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Allow imports from the shared package when running standalone
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from shared.ado_client import ADOClient, BuildFailure
from shared.utils import parse_pipeline_ids

logger = logging.getLogger(__name__)


class BuildFailureFetcher:
    """Fetches and enriches failed pipeline runs from Azure DevOps."""

    def __init__(self, ado_client: ADOClient | None = None) -> None:
        self._client = ado_client or ADOClient()

    def fetch(
        self,
        pipeline_ids: list[int] | None = None,
        top: int | None = None,
    ) -> list[BuildFailure]:
        """
        Retrieve failed builds and enrich with timeline/error data.

        Args:
            pipeline_ids: ADO pipeline definition IDs to include.
                          Falls back to ADO_PIPELINE_IDS env var when None.
            top: Maximum number of failed builds to retrieve.
                 Falls back to MAX_BUILD_RUNS env var (default 100).

        Returns:
            List of enriched :class:`BuildFailure` objects.
        """
        if pipeline_ids is None:
            raw = os.environ.get("ADO_PIPELINE_IDS", "")
            pipeline_ids = parse_pipeline_ids(raw) or None

        if top is None:
            top = int(os.environ.get("MAX_BUILD_RUNS", "100"))

        logger.info(
            "Fetching failed builds (pipeline_ids=%s, top=%d)",
            pipeline_ids,
            top,
        )
        failures = self._client.extract_build_failures(
            pipeline_ids=pipeline_ids,
            top=top,
        )
        logger.info("Fetched %d failure records", len(failures))
        return failures
