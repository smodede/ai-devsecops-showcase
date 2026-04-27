"""
Orchestrator — Scenario 2: AI PR Compliance.

Entry point that wires together:
  1. ConfluenceFetcher  — pull engineering standards from Confluence
  2. ADOClient          — fetch PR files changed in the pull request
  3. ComplianceChecker  — GPT-powered compliance check
  4. PRReviewer         — post comment + set PR status (block on FAIL)

Can run in two modes:
  - CLI mode: python -m agent.orchestrator --pr-id <ID>
  - Serve mode: python -m agent.orchestrator --serve
    (starts a FastAPI webhook server that processes ADO service hook events)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from shared.ado_client import ADOClient
from shared.utils import configure_logging

from .compliance_checker import ComplianceChecker
from .confluence_fetcher import ConfluenceFetcher
from .pr_reviewer import PRReviewer

logger = logging.getLogger(__name__)


def run_for_pr(
    pr_id: int,
    repo_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Run the full PR compliance check for a single pull request.

    Args:
        pr_id: Azure DevOps pull request ID.
        repo_id: Repository GUID (falls back to ADO_REPOSITORY_ID env var).
        dry_run: When True, skip posting comment/status to ADO.

    Returns:
        Dict with keys: pr_id, verdict, findings_count, comment_thread_id,
        status_state (and markdown if dry_run=True).
    """
    configure_logging()
    logger.info("=== AI PR Compliance — starting review for PR %d ===", pr_id)

    repo_id = repo_id or os.environ.get("ADO_REPOSITORY_ID", "")

    # 1. Fetch standards from Confluence
    confluence = ConfluenceFetcher()
    standards = confluence.fetch_all_standards()
    logger.info("Loaded %d standards documents", len(standards))

    # 2. Fetch PR files from ADO
    ado = ADOClient()
    changed_files = ado.get_pr_files(repo_id=repo_id, pr_id=pr_id)

    # Collect YAML / code files (skip binaries)
    TEXT_EXTENSIONS = {".yml", ".yaml", ".py", ".json", ".tf", ".sh", ".md", ".txt", ".cfg", ".ini", ".toml"}
    files_to_review: dict[str, str] = {}

    for entry in changed_files:
        item = entry.get("item", {})
        path: str = item.get("path", "")
        if not path:
            continue
        ext = Path(path).suffix.lower()
        if ext not in TEXT_EXTENSIONS:
            logger.debug("Skipping non-text file: %s", path)
            continue
        try:
            content = ado.get_file_content(repo_id=repo_id, path=path)
            files_to_review[path] = content
        except Exception:
            logger.warning("Could not fetch content for file '%s'", path)

    if not files_to_review:
        logger.info("No reviewable files found in PR %d.", pr_id)
        return {"pr_id": pr_id, "verdict": "PASS", "findings_count": 0, "note": "No reviewable files"}

    logger.info("Reviewing %d files in PR %d", len(files_to_review), pr_id)

    # 3. Run compliance check
    checker = ComplianceChecker()
    report = checker.check(files=files_to_review, standards=standards)

    result: dict = {
        "pr_id": pr_id,
        "verdict": report.verdict,
        "findings_count": len(report.findings),
    }

    # 4. Post results (or dry-run)
    if dry_run:
        from .pr_reviewer import _render_comment
        result["markdown"] = _render_comment(report, pr_id)
        logger.info("Dry run — PR comment/status skipped. Markdown captured.")
    else:
        reviewer = PRReviewer(ado_client=ado)
        review_result = reviewer.review(pr_id=pr_id, report=report, repo_id=repo_id)
        result["comment_thread_id"] = review_result.comment_thread_id
        result["status_state"] = review_result.status_state

    logger.info("=== AI PR Compliance — review complete: %s ===", result)
    return result


def serve(host: str = "0.0.0.0", port: int = 8080) -> None:
    """
    Start a FastAPI webhook server that handles Azure DevOps service hook events.

    ADO sends a POST to /webhook/pr-created (or /webhook/pr-updated) when a
    PR is opened or updated. The server runs the compliance check automatically.
    """
    try:
        import uvicorn
        from fastapi import FastAPI, Request, HTTPException
    except ImportError as exc:
        logger.error(
            "FastAPI/uvicorn not installed. Run: pip install fastapi uvicorn\n%s", exc
        )
        sys.exit(1)

    configure_logging()
    app = FastAPI(title="AI PR Compliance Webhook")

    @app.post("/webhook/pr-created")
    @app.post("/webhook/pr-updated")
    async def handle_pr_event(request: Request) -> dict:
        payload = await request.json()
        resource = payload.get("resource", {})
        pr_id = resource.get("pullRequestId")
        repo_id = resource.get("repository", {}).get("id", "")

        if not pr_id:
            raise HTTPException(status_code=400, detail="Missing pullRequestId in payload")

        logger.info("Received PR event: pr_id=%s repo_id=%s", pr_id, repo_id)
        result = run_for_pr(pr_id=int(pr_id), repo_id=repo_id or None)
        return result

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    logger.info("Starting PR Compliance webhook server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI PR Compliance — Scenario 2")
    parser.add_argument("--pr-id", type=int, help="Pull request ID to review (CLI mode)")
    parser.add_argument("--repo-id", type=str, help="ADO repository GUID")
    parser.add_argument("--dry-run", action="store_true", help="Skip posting to ADO")
    parser.add_argument("--serve", action="store_true", help="Start webhook server")
    parser.add_argument("--host", default="0.0.0.0", help="Webhook server host")
    parser.add_argument("--port", type=int, default=8080, help="Webhook server port")
    args = parser.parse_args()

    if args.serve:
        serve(host=args.host, port=args.port)
    elif args.pr_id:
        outcome = run_for_pr(
            pr_id=args.pr_id,
            repo_id=args.repo_id,
            dry_run=args.dry_run,
        )
        if args.dry_run and "markdown" in outcome:
            print(outcome["markdown"])
        else:
            print(outcome)
    else:
        parser.print_help()
        sys.exit(1)
