"""
Failure Pattern Miner — Scenario 1.

Groups raw build failures into candidate clusters using simple
heuristics (task name + error prefix) before handing off to the
GPT-based root cause clusterer.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field

from shared.ado_client import BuildFailure
from shared.utils import truncate

logger = logging.getLogger(__name__)

# Maximum characters to retain per individual error message before clustering
_ERROR_TRUNCATION = 400


@dataclass
class FailurePattern:
    """A named group of similar build failures."""

    pattern_key: str
    failures: list[BuildFailure] = field(default_factory=list)
    representative_errors: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.failures)

    @property
    def pipeline_names(self) -> list[str]:
        return sorted({f.pipeline_name for f in self.failures})

    @property
    def branches(self) -> list[str]:
        return sorted({f.branch for f in self.failures})


def _normalise_error(msg: str) -> str:
    """Strip volatile tokens (GUIDs, timestamps, paths) from error messages."""
    msg = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<GUID>", msg, flags=re.I)
    msg = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", "<TIMESTAMP>", msg)
    msg = re.sub(r"(?:/[\w.\-]+)+", "<PATH>", msg)
    msg = re.sub(r"\b\d{4,}\b", "<NUM>", msg)
    return msg.strip()


def _task_key(failure: BuildFailure) -> str:
    """Derive a grouping key from the first failed task name."""
    if failure.failed_tasks:
        task_name = failure.failed_tasks[0].get("name", "unknown-task")
    else:
        task_name = "unknown-task"
    return task_name.lower().replace(" ", "-")


def _error_prefix(failure: BuildFailure, prefix_len: int = 80) -> str:
    """Return a short, normalised prefix of the first error message."""
    if failure.error_messages:
        return _normalise_error(failure.error_messages[0])[:prefix_len]
    return "no-error-message"


class FailurePatternMiner:
    """
    Groups :class:`BuildFailure` objects into :class:`FailurePattern` clusters
    using lightweight heuristic matching.
    """

    def __init__(self, min_cluster_size: int = 1) -> None:
        self.min_cluster_size = min_cluster_size

    def mine(self, failures: list[BuildFailure]) -> list[FailurePattern]:
        """
        Group failures into patterns.

        Args:
            failures: List of enriched build failures.

        Returns:
            List of :class:`FailurePattern` objects sorted by frequency (desc).
        """
        if not failures:
            logger.info("No failures to mine.")
            return []

        buckets: dict[str, list[BuildFailure]] = defaultdict(list)

        for failure in failures:
            key = f"{_task_key(failure)}::{_error_prefix(failure)}"
            buckets[key].append(failure)

        patterns: list[FailurePattern] = []
        for key, bucket in buckets.items():
            if len(bucket) < self.min_cluster_size:
                continue

            representative_errors = list(
                {
                    truncate(_normalise_error(err), _ERROR_TRUNCATION)
                    for f in bucket
                    for err in f.error_messages[:3]
                }
            )[:5]

            patterns.append(
                FailurePattern(
                    pattern_key=key,
                    failures=bucket,
                    representative_errors=representative_errors,
                )
            )

        patterns.sort(key=lambda p: p.count, reverse=True)
        logger.info(
            "Mined %d patterns from %d failures (min_cluster_size=%d)",
            len(patterns),
            len(failures),
            self.min_cluster_size,
        )
        return patterns
