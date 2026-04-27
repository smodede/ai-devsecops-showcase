"""
MCP Tool Definitions — Scenario 2: AI PR Compliance.

Exposes compliance review steps as callable MCP tools.
"""

from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from agent.confluence_fetcher import ConfluenceFetcher, StandardsDocument
from agent.compliance_checker import ComplianceChecker, ComplianceReport, ComplianceFinding
from agent.pr_reviewer import PRReviewer, _render_comment


def tool_fetch_confluence_standards(
    space_keys: list[str] | None = None,
    extra_page_ids: list[str] | None = None,
) -> list[dict]:
    """MCP tool: fetch engineering standards from Confluence."""
    fetcher = ConfluenceFetcher()
    docs = fetcher.fetch_all_standards(
        space_keys=space_keys,
        extra_page_ids=extra_page_ids,
    )
    return [
        {
            "page_id": d.page_id,
            "title": d.title,
            "space_key": d.space_key,
            "url": d.url,
            "content": d.content,
            "last_modified": d.last_modified,
            "labels": d.labels,
        }
        for d in docs
    ]


def tool_get_pr_files(pr_id: int, repo_id: str) -> list[dict]:
    """MCP tool: retrieve changed files in a PR."""
    from shared.ado_client import ADOClient
    ado = ADOClient()
    return ado.get_pr_files(repo_id=repo_id, pr_id=pr_id)


def tool_check_compliance(
    files: dict[str, str],
    standards: list[dict],
) -> dict:
    """MCP tool: run compliance check against standards."""
    std_objects = [
        StandardsDocument(
            page_id=s["page_id"],
            title=s["title"],
            space_key=s["space_key"],
            url=s["url"],
            content=s["content"],
            last_modified=s.get("last_modified", ""),
            labels=s.get("labels", []),
        )
        for s in standards
    ]

    checker = ComplianceChecker()
    report = checker.check(files=files, standards=std_objects)

    return {
        "verdict": report.verdict,
        "summary": report.summary,
        "findings": [
            {
                "file": f.file,
                "severity": f.severity,
                "rule": f.rule,
                "description": f.description,
                "line_hint": f.line_hint,
                "recommendation": f.recommendation,
            }
            for f in report.findings
        ],
        "compliant_items": report.compliant_items,
    }


def tool_post_pr_review(
    pr_id: int,
    repo_id: str,
    report: dict,
    dry_run: bool = False,
) -> dict:
    """MCP tool: post compliance review to PR and set status."""
    report_obj = ComplianceReport(
        verdict=report["verdict"],
        summary=report["summary"],
        findings=[
            ComplianceFinding(
                file=f["file"],
                severity=f["severity"],
                rule=f["rule"],
                description=f["description"],
                line_hint=f.get("line_hint", ""),
                recommendation=f.get("recommendation", ""),
            )
            for f in report.get("findings", [])
        ],
        compliant_items=report.get("compliant_items", []),
    )

    if dry_run:
        return {"dry_run": True, "markdown": _render_comment(report_obj, pr_id)}

    reviewer = PRReviewer()
    result = reviewer.review(pr_id=pr_id, report=report_obj, repo_id=repo_id)
    return {
        "dry_run": False,
        "verdict": result.verdict,
        "comment_thread_id": result.comment_thread_id,
        "status_state": result.status_state,
    }


# Tool registry for MCP framework discovery
MCP_TOOLS = {
    "fetch_confluence_standards": tool_fetch_confluence_standards,
    "get_pr_files": tool_get_pr_files,
    "check_compliance": tool_check_compliance,
    "post_pr_review": tool_post_pr_review,
}
