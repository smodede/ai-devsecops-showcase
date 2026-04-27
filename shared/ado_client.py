"""
Azure DevOps REST API client.

Wraps the azure-devops Python SDK with convenience methods used by both
scenarios: fetching build timelines, posting PR comments, and updating
Wiki pages.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class BuildFailure:
    """Represents a single failed pipeline run."""

    build_id: int
    pipeline_name: str
    pipeline_id: int
    branch: str
    start_time: str
    finish_time: str
    reason: str
    requested_by: str
    failed_tasks: list[dict[str, Any]] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    logs_url: str = ""


@dataclass
class PRComment:
    """Represents a comment to be posted on a pull request."""

    content: str
    status: str = "active"  # active | resolved | wontFix | closed | byDesign | pending
    comment_type: int = 1   # 1 = text


class ADOClient:
    """
    Thin REST wrapper for Azure DevOps.

    Uses the ADO REST API v7.1 directly (rather than the SDK) so that
    there are no complex auth adapter dependencies.
    """

    API_VERSION = "7.1"

    def __init__(
        self,
        organization_url: str | None = None,
        project: str | None = None,
        pat: str | None = None,
    ) -> None:
        self.organization_url = (
            organization_url or os.environ.get("ADO_ORGANIZATION_URL", "")
        ).rstrip("/")
        self.project = project or os.environ.get("ADO_PROJECT", "")
        pat = pat or os.environ.get("ADO_PAT", "")

        if not self.organization_url:
            raise EnvironmentError("ADO_ORGANIZATION_URL is not set.")
        if not self.project:
            raise EnvironmentError("ADO_PROJECT is not set.")
        if not pat:
            raise EnvironmentError("ADO_PAT is not set.")

        token = base64.b64encode(f":{pat}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

        self._session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session.headers.update(self._headers)

        logger.info(
            "ADOClient initialised (org=%s, project=%s)", self.organization_url, self.project
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str, subdomain: str = "") -> str:
        """Build a full ADO REST URL."""
        if subdomain:
            base = self.organization_url.replace("https://", f"https://{subdomain}.")
        else:
            base = self.organization_url
        return f"{base}/{self.project}/_apis/{path}"

    def _get(self, url: str, params: dict | None = None) -> Any:
        resp = self._session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, url: str, body: dict) -> Any:
        resp = self._session.post(url, json=body)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, url: str, body: dict | list, extra_headers: dict | None = None) -> Any:
        headers = {**self._headers, **(extra_headers or {})}
        resp = self._session.patch(url, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _put(self, url: str, body: dict, extra_headers: dict | None = None, params: dict | None = None) -> Any:
        headers = {**self._headers, **(extra_headers or {})}
        resp = self._session.put(url, json=body, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Build / Pipeline methods
    # ------------------------------------------------------------------

    def get_builds(
        self,
        pipeline_ids: list[int] | None = None,
        result: str = "failed",
        top: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch build runs filtered by result.

        Args:
            pipeline_ids: Optional list of pipeline definition IDs to filter by.
            result: Build result filter (failed | succeeded | partiallySucceeded | canceled).
            top: Maximum number of builds to return.

        Returns:
            List of build dicts from the ADO API.
        """
        params: dict[str, Any] = {
            "api-version": self.API_VERSION,
            "resultFilter": result,
            "$top": top,
        }
        if pipeline_ids:
            params["definitions"] = ",".join(str(p) for p in pipeline_ids)

        url = self._url("build/builds")
        data = self._get(url, params=params)
        builds: list[dict[str, Any]] = data.get("value", [])
        logger.info("Fetched %d builds (result=%s)", len(builds), result)
        return builds

    def get_build_timeline(self, build_id: int) -> dict[str, Any]:
        """Fetch the timeline records for a build (contains task-level detail)."""
        url = self._url(f"build/builds/{build_id}/timeline")
        return self._get(url, params={"api-version": self.API_VERSION})

    def get_build_log(self, build_id: int, log_id: int) -> str:
        """Fetch the text content of a specific build log."""
        url = self._url(f"build/builds/{build_id}/logs/{log_id}")
        resp = self._session.get(
            url,
            params={"api-version": self.API_VERSION},
            headers={**self._headers, "Accept": "text/plain"},
        )
        resp.raise_for_status()
        return resp.text

    def extract_build_failures(
        self,
        pipeline_ids: list[int] | None = None,
        top: int = 100,
    ) -> list[BuildFailure]:
        """
        High-level helper: fetch failed builds and enrich with timeline data.

        Returns a list of :class:`BuildFailure` objects ready for analysis.
        """
        raw_builds = self.get_builds(pipeline_ids=pipeline_ids, result="failed", top=top)
        failures: list[BuildFailure] = []

        for build in raw_builds:
            build_id = build["id"]
            try:
                timeline = self.get_build_timeline(build_id)
                records = timeline.get("records", [])

                failed_tasks = [
                    r for r in records
                    if r.get("result") == "failed" and r.get("type") == "Task"
                ]
                error_messages = [
                    issue["message"]
                    for r in records
                    for issue in r.get("issues", [])
                    if issue.get("type") == "error"
                ]

                failure = BuildFailure(
                    build_id=build_id,
                    pipeline_name=build.get("definition", {}).get("name", "unknown"),
                    pipeline_id=build.get("definition", {}).get("id", 0),
                    branch=build.get("sourceBranch", ""),
                    start_time=build.get("startTime", ""),
                    finish_time=build.get("finishTime", ""),
                    reason=build.get("reason", ""),
                    requested_by=build.get("requestedBy", {}).get("displayName", ""),
                    failed_tasks=failed_tasks,
                    error_messages=error_messages,
                )
                failures.append(failure)
            except Exception:
                logger.exception("Failed to enrich build %d", build_id)

        logger.info("Extracted %d enriched failure records", len(failures))
        return failures

    # ------------------------------------------------------------------
    # Pull Request methods
    # ------------------------------------------------------------------

    def get_pull_request(self, repo_id: str, pr_id: int) -> dict[str, Any]:
        """Fetch details for a specific pull request."""
        url = self._url(f"git/repositories/{repo_id}/pullrequests/{pr_id}")
        return self._get(url, params={"api-version": self.API_VERSION})

    def get_pr_files(self, repo_id: str, pr_id: int) -> list[dict[str, Any]]:
        """Fetch the list of changed files in a pull request."""
        url = self._url(f"git/repositories/{repo_id}/pullrequests/{pr_id}/iterations")
        iterations = self._get(url, params={"api-version": self.API_VERSION})
        iteration_id = iterations.get("count", 1)

        url2 = self._url(
            f"git/repositories/{repo_id}/pullrequests/{pr_id}/iterations/{iteration_id}/changes"
        )
        changes = self._get(url2, params={"api-version": self.API_VERSION})
        return changes.get("changeEntries", [])

    def get_file_content(self, repo_id: str, path: str, version: str = "main") -> str:
        """Fetch the raw content of a file from the repository."""
        url = self._url(f"git/repositories/{repo_id}/items")
        params = {
            "api-version": self.API_VERSION,
            "path": path,
            "versionDescriptor.version": version,
            "includeContent": "true",
        }
        resp = self._session.get(url, params=params)
        resp.raise_for_status()
        return resp.text

    def post_pr_comment(
        self,
        repo_id: str,
        pr_id: int,
        comment: PRComment,
        thread_context: dict | None = None,
    ) -> dict[str, Any]:
        """
        Post a comment thread on a pull request.

        Args:
            repo_id: Repository GUID or name.
            pr_id: Pull request ID.
            comment: The comment to post.
            thread_context: Optional file path / line position context for inline comments.

        Returns:
            Created thread dict from the ADO API.
        """
        url = self._url(f"git/repositories/{repo_id}/pullrequests/{pr_id}/threads")
        body: dict[str, Any] = {
            "comments": [
                {
                    "parentCommentId": 0,
                    "content": comment.content,
                    "commentType": comment.comment_type,
                }
            ],
            "status": comment.status,
        }
        if thread_context:
            body["threadContext"] = thread_context

        result = self._post(url + f"?api-version={self.API_VERSION}", body)
        logger.info("Posted PR comment thread on PR %d", pr_id)
        return result

    def set_pr_vote(
        self,
        repo_id: str,
        pr_id: int,
        reviewer_id: str,
        vote: int,
    ) -> dict[str, Any]:
        """
        Set a reviewer vote on a pull request.

        Vote values: 10=approved, 5=approved with suggestions,
        0=no vote, -5=waiting for author, -10=rejected.
        """
        url = self._url(
            f"git/repositories/{repo_id}/pullrequests/{pr_id}/reviewers/{reviewer_id}"
        )
        return self._put(url + f"?api-version={self.API_VERSION}", {"vote": vote})

    def update_pr_status(
        self,
        repo_id: str,
        pr_id: int,
        state: str,
        description: str,
        context_name: str = "ai-compliance",
        context_genre: str = "ai-devsecops",
    ) -> dict[str, Any]:
        """
        Post a custom status to a pull request (used to block/approve via branch policy).

        Args:
            repo_id: Repository GUID or name.
            pr_id: Pull request ID.
            state: 'succeeded' | 'failed' | 'pending' | 'error' | 'notSet' | 'notApplicable'
            description: Human-readable description shown in the PR.
            context_name: Status context name (uniquely identifies this check).
            context_genre: Status context genre (groups related statuses).

        Returns:
            Created status dict from the ADO API.
        """
        url = self._url(f"git/repositories/{repo_id}/pullrequests/{pr_id}/statuses")
        body = {
            "state": state,
            "description": description,
            "context": {
                "name": context_name,
                "genre": context_genre,
            },
        }
        result = self._post(url + f"?api-version={self.API_VERSION}", body)
        logger.info(
            "Updated PR %d status: state=%s context=%s/%s",
            pr_id, state, context_genre, context_name,
        )
        return result

    # ------------------------------------------------------------------
    # Wiki methods
    # ------------------------------------------------------------------

    def get_wiki_page(self, wiki_id: str, path: str) -> dict[str, Any]:
        """Fetch an existing Wiki page."""
        url = (
            f"{self.organization_url}/{self.project}/_apis/wiki/wikis/{wiki_id}/pages"
        )
        params = {"api-version": self.API_VERSION, "path": path, "includeContent": "true"}
        return self._get(url, params=params)

    def upsert_wiki_page(
        self,
        wiki_id: str,
        path: str,
        content: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        """
        Create or update a Wiki page with the given Markdown content.

        Args:
            wiki_id: The Wiki identifier.
            path: Page path (e.g. '/Build-Intelligence/Failure-Report').
            content: Markdown content for the page.
            version: ETag version string for update (omit for create).

        Returns:
            API response dict.
        """
        url = (
            f"{self.organization_url}/{self.project}/_apis/wiki/wikis/{wiki_id}/pages"
        )
        params = {"api-version": self.API_VERSION, "path": path}
        extra_headers: dict[str, str] = {}
        if version:
            extra_headers["If-Match"] = version

        result = self._put(url, {"content": content}, extra_headers=extra_headers, params=params)
        logger.info("Upserted Wiki page: wiki=%s path=%s", wiki_id, path)
        return result

    def get_wiki_page_version(self, wiki_id: str, path: str) -> str | None:
        """Return the ETag version of an existing wiki page, or None if it doesn't exist."""
        try:
            page = self.get_wiki_page(wiki_id, path)
            return page.get("eTag")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise
