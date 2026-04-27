"""
MCP Tool Definitions — Scenario 1: AI Build Intelligence.

Exposes the agent steps as callable tools that can be invoked by an
MCP-aware runner or orchestration framework.
"""

from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from agent.build_failure_fetcher import BuildFailureFetcher
from agent.failure_pattern_miner import FailurePatternMiner
from agent.root_cause_clusterer import RootCauseClusterer
from agent.wiki_publisher import WikiPublisher, render_wiki_page


def tool_get_failed_builds(
    pipeline_ids: list[int] | None = None,
    top: int = 100,
) -> list[dict]:
    """MCP tool: fetch and return failed build records."""
    fetcher = BuildFailureFetcher()
    failures = fetcher.fetch(pipeline_ids=pipeline_ids, top=top)
    return [
        {
            "build_id": f.build_id,
            "pipeline_name": f.pipeline_name,
            "pipeline_id": f.pipeline_id,
            "branch": f.branch,
            "start_time": f.start_time,
            "finish_time": f.finish_time,
            "reason": f.reason,
            "requested_by": f.requested_by,
            "failed_tasks": f.failed_tasks,
            "error_messages": f.error_messages,
        }
        for f in failures
    ]


def tool_mine_failure_patterns(
    failures: list[dict],
    min_cluster_size: int = 2,
) -> list[dict]:
    """MCP tool: mine heuristic failure patterns from raw failure records."""
    from shared.ado_client import BuildFailure

    failure_objects = [
        BuildFailure(
            build_id=f["build_id"],
            pipeline_name=f["pipeline_name"],
            pipeline_id=f["pipeline_id"],
            branch=f["branch"],
            start_time=f["start_time"],
            finish_time=f["finish_time"],
            reason=f["reason"],
            requested_by=f["requested_by"],
            failed_tasks=f.get("failed_tasks", []),
            error_messages=f.get("error_messages", []),
        )
        for f in failures
    ]

    miner = FailurePatternMiner(min_cluster_size=min_cluster_size)
    patterns = miner.mine(failure_objects)

    return [
        {
            "pattern_key": p.pattern_key,
            "count": p.count,
            "pipeline_names": p.pipeline_names,
            "branches": p.branches,
            "representative_errors": p.representative_errors,
            "failure_ids": [f.build_id for f in p.failures],
        }
        for p in patterns
    ]


def tool_analyse_root_causes(patterns: list[dict]) -> list[dict]:
    """MCP tool: run GPT root cause analysis on heuristic patterns."""
    from agent.failure_pattern_miner import FailurePattern
    from shared.ado_client import BuildFailure

    pattern_objects = [
        FailurePattern(
            pattern_key=p["pattern_key"],
            failures=[
                BuildFailure(
                    build_id=bid,
                    pipeline_name=p["pipeline_names"][0] if p["pipeline_names"] else "",
                    pipeline_id=0,
                    branch=p["branches"][0] if p["branches"] else "",
                    start_time="",
                    finish_time="",
                    reason="",
                    requested_by="",
                )
                for bid in p.get("failure_ids", [])
            ],
            representative_errors=p.get("representative_errors", []),
        )
        for p in patterns
    ]

    clusterer = RootCauseClusterer()
    findings = clusterer.analyse(pattern_objects)

    return [
        {
            "title": f.title,
            "severity": f.severity,
            "root_cause": f.root_cause,
            "remediation_steps": f.remediation_steps,
            "affected_pipelines": f.affected_pipelines,
            "affected_branches": f.affected_branches,
            "occurrence_count": f.pattern.count,
        }
        for f in findings
    ]


def tool_publish_wiki_report(
    findings: list[dict],
    dry_run: bool = False,
) -> dict:
    """MCP tool: publish findings to an Azure DevOps Wiki page."""
    from agent.root_cause_clusterer import RootCauseFinding
    from agent.failure_pattern_miner import FailurePattern

    finding_objects = [
        RootCauseFinding(
            pattern=FailurePattern(
                pattern_key=f.get("title", "unknown"),
                failures=[],
                representative_errors=[],
            ),
            raw_json=f,
        )
        for f in findings
    ]

    if dry_run:
        markdown = render_wiki_page(finding_objects)
        return {"dry_run": True, "markdown": markdown}

    publisher = WikiPublisher()
    wiki_path = publisher.publish(finding_objects)
    return {"dry_run": False, "wiki_path": wiki_path}


# Tool registry for MCP framework discovery
MCP_TOOLS = {
    "get_failed_builds": tool_get_failed_builds,
    "mine_failure_patterns": tool_mine_failure_patterns,
    "analyse_root_causes": tool_analyse_root_causes,
    "publish_wiki_report": tool_publish_wiki_report,
}
