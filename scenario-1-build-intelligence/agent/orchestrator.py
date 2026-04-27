"""
Orchestrator — Scenario 1: AI Build Intelligence.

Entry point that wires together:
  1. BuildFailureFetcher   — pull recent failures from Azure DevOps
  2. FailurePatternMiner   — heuristically cluster failures
  3. RootCauseClusterer    — GPT-powered root cause + remediation
  4. WikiPublisher         — render Markdown and upsert to ADO Wiki
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure the repo root is on the path so 'shared' is importable
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from shared.utils import configure_logging

from .build_failure_fetcher import BuildFailureFetcher
from .failure_pattern_miner import FailurePatternMiner
from .root_cause_clusterer import RootCauseClusterer
from .wiki_publisher import WikiPublisher

logger = logging.getLogger(__name__)


def run(
    pipeline_ids: list[int] | None = None,
    top: int | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Execute the full Build Intelligence pipeline.

    Args:
        pipeline_ids: ADO pipeline definition IDs to analyse.
                      Falls back to ADO_PIPELINE_IDS env var.
        top: Maximum number of failed builds to analyse.
             Falls back to MAX_BUILD_RUNS env var.
        dry_run: When True, skip Wiki publishing and return the rendered
                 Markdown in the result dict instead.

    Returns:
        Dict with keys: failures_count, patterns_count, findings_count,
        wiki_path (or markdown if dry_run=True).
    """
    configure_logging()
    logger.info("=== AI Build Intelligence — starting analysis ===")

    # 1. Fetch failures
    fetcher = BuildFailureFetcher()
    failures = fetcher.fetch(pipeline_ids=pipeline_ids, top=top)

    if not failures:
        logger.info("No failures found — nothing to analyse.")
        return {"failures_count": 0, "patterns_count": 0, "findings_count": 0}

    # 2. Mine patterns
    min_cluster = int(os.environ.get("MIN_CLUSTER_SIZE", "2"))
    miner = FailurePatternMiner(min_cluster_size=min_cluster)
    patterns = miner.mine(failures)

    if not patterns:
        logger.info("No patterns met the minimum cluster size threshold.")
        return {
            "failures_count": len(failures),
            "patterns_count": 0,
            "findings_count": 0,
        }

    # 3. GPT root cause analysis
    clusterer = RootCauseClusterer()
    findings = clusterer.analyse(patterns)

    # Sort findings by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings.sort(key=lambda f: severity_order.get(f.severity, 99))

    result: dict = {
        "failures_count": len(failures),
        "patterns_count": len(patterns),
        "findings_count": len(findings),
    }

    # 4. Publish to Wiki (or dry-run)
    if dry_run:
        from .wiki_publisher import render_wiki_page
        result["markdown"] = render_wiki_page(findings)
        logger.info("Dry run — Wiki publish skipped. Markdown captured in result.")
    else:
        publisher = WikiPublisher()
        wiki_path = publisher.publish(findings)
        result["wiki_path"] = wiki_path

    logger.info("=== AI Build Intelligence — analysis complete: %s ===", result)
    return result


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    outcome = run(dry_run=dry)
    if dry and "markdown" in outcome:
        print(outcome["markdown"])
    else:
        print(outcome)
