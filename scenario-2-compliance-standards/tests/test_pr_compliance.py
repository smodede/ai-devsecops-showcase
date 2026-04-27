"""
Unit tests for Scenario 2 — AI PR Compliance.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scenario-2 directory is at sys.path[0] (not scenario-1's agent)
_scenario_dir = Path(__file__).resolve().parents[1]
_repo_root = _scenario_dir.parent

# Clear any stale 'agent' module that may have been imported from another scenario
for _key in list(sys.modules.keys()):
    if _key == "agent" or _key.startswith("agent."):
        del sys.modules[_key]

for _p in [str(_repo_root), str(_scenario_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
# Ensure THIS scenario's directory is always first
if sys.path[0] != str(_scenario_dir):
    sys.path.remove(str(_scenario_dir))
    sys.path.insert(0, str(_scenario_dir))

from agent.confluence_fetcher import ConfluenceFetcher, StandardsDocument
from agent.compliance_checker import (
    ComplianceChecker,
    ComplianceReport,
    ComplianceFinding,
    _build_standards_context,
    _build_files_context,
)
from agent.pr_reviewer import PRReviewer, _render_comment, ReviewResult


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_standards_doc(
    page_id: str = "1",
    title: str = "Pipeline Standards",
    content: str = "All pipelines must use approved base images.",
) -> StandardsDocument:
    return StandardsDocument(
        page_id=page_id,
        title=title,
        space_key="ENG",
        url="https://example.atlassian.net/wiki/spaces/ENG/pages/1",
        content=content,
        last_modified="2024-01-01T00:00:00Z",
        labels=["standards", "devops"],
    )


def make_compliance_report(
    verdict: str = "PASS",
    findings: list[ComplianceFinding] | None = None,
) -> ComplianceReport:
    return ComplianceReport(
        verdict=verdict,
        summary="All checks passed." if verdict == "PASS" else "Violations found.",
        findings=findings or [],
        compliant_items=["Approved base image used"] if verdict == "PASS" else [],
    )


def make_finding(
    severity: str = "HIGH",
    rule: str = "approved-base-image",
    file: str = "azure-pipelines.yml",
) -> ComplianceFinding:
    return ComplianceFinding(
        file=file,
        severity=severity,
        rule=rule,
        description="Unapproved Docker base image detected.",
        line_hint="Line 12",
        recommendation="Use ubuntu-22.04 as specified in standards.",
    )


# ---------------------------------------------------------------------------
# ConfluenceFetcher tests (unit — no real HTTP)
# ---------------------------------------------------------------------------

class TestConfluenceFetcherInit:
    def test_raises_when_url_missing(self, monkeypatch):
        monkeypatch.delenv("CONFLUENCE_URL", raising=False)
        monkeypatch.setenv("CONFLUENCE_USERNAME", "user@example.com")
        monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token123")
        with pytest.raises(EnvironmentError, match="CONFLUENCE_URL"):
            ConfluenceFetcher()

    def test_raises_when_username_missing(self, monkeypatch):
        monkeypatch.setenv("CONFLUENCE_URL", "https://example.atlassian.net")
        monkeypatch.delenv("CONFLUENCE_USERNAME", raising=False)
        monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token123")
        with pytest.raises(EnvironmentError, match="CONFLUENCE_USERNAME"):
            ConfluenceFetcher()

    def test_raises_when_token_missing(self, monkeypatch):
        monkeypatch.setenv("CONFLUENCE_URL", "https://example.atlassian.net")
        monkeypatch.setenv("CONFLUENCE_USERNAME", "user@example.com")
        monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)
        with pytest.raises(EnvironmentError, match="CONFLUENCE_API_TOKEN"):
            ConfluenceFetcher()

    def test_strip_html_removes_tags(self):
        html = "<h1>Title</h1><p>This is <b>bold</b> text &amp; more.</p>"
        result = ConfluenceFetcher._strip_html(html)
        assert "<" not in result
        assert ">" not in result
        assert "&" in result  # decoded
        assert "bold" in result
        assert "Title" in result

    def test_strip_html_decodes_entities(self):
        html = "A &lt;tag&gt; &amp; &quot;quote&quot; &nbsp;space"
        result = ConfluenceFetcher._strip_html(html)
        assert "<tag>" in result
        assert "&" in result
        assert '"quote"' in result


# ---------------------------------------------------------------------------
# ComplianceChecker tests
# ---------------------------------------------------------------------------

class TestBuildStandardsContext:
    def test_empty_standards_returns_empty_string(self):
        result = _build_standards_context([])
        assert result == ""

    def test_multiple_standards_combined(self):
        docs = [make_standards_doc("1", "Doc A", "Content A"), make_standards_doc("2", "Doc B", "Content B")]
        result = _build_standards_context(docs)
        assert "Doc A" in result
        assert "Content A" in result
        assert "Doc B" in result

    def test_truncation_at_limit(self):
        long_content = "x" * 15_000
        doc = make_standards_doc(content=long_content)
        result = _build_standards_context([doc])
        assert len(result) <= 13_000  # Allow some overhead for title/headers


class TestBuildFilesContext:
    def test_formats_file_with_path(self):
        result = _build_files_context({"path/to/file.yml": "trigger: none"})
        assert "path/to/file.yml" in result
        assert "trigger: none" in result

    def test_multiple_files_all_present(self):
        files = {"a.yml": "content a", "b.py": "content b"}
        result = _build_files_context(files)
        assert "a.yml" in result
        assert "b.py" in result


class TestComplianceChecker:
    def test_empty_files_returns_pass(self):
        checker = ComplianceChecker(openai_client=MagicMock())
        report = checker.check(files={}, standards=[])
        assert report.verdict == "PASS"

    def test_gpt_pass_response(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = (
            '{"verdict": "PASS", "summary": "All good.", '
            '"findings": [], "compliant_items": ["Approved image used"]}'
        )
        checker = ComplianceChecker(openai_client=mock_client)
        report = checker.check(
            files={"pipeline.yml": "trigger: none\npool:\n  vmImage: ubuntu-22.04"},
            standards=[make_standards_doc()],
        )
        assert report.verdict == "PASS"
        assert report.is_passing
        assert report.findings == []
        assert "Approved image used" in report.compliant_items

    def test_gpt_fail_response_with_findings(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = (
            '{"verdict": "FAIL", "summary": "Violations found.", '
            '"findings": [{"file": "pipeline.yml", "severity": "HIGH", '
            '"rule": "approved-base-image", '
            '"description": "Unapproved image.", '
            '"line_hint": "Line 5", '
            '"recommendation": "Use ubuntu-22.04"}], '
            '"compliant_items": []}'
        )
        checker = ComplianceChecker(openai_client=mock_client)
        report = checker.check(
            files={"pipeline.yml": "pool:\n  vmImage: windows-2019"},
            standards=[make_standards_doc()],
        )
        assert report.verdict == "FAIL"
        assert not report.is_passing
        assert len(report.findings) == 1
        assert report.findings[0].severity == "HIGH"
        assert report.high_findings

    def test_invalid_json_returns_fail(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = "This is not valid JSON"
        checker = ComplianceChecker(openai_client=mock_client)
        report = checker.check(
            files={"file.yml": "content"},
            standards=[],
        )
        assert report.verdict == "FAIL"

    def test_critical_findings_property(self):
        findings = [
            make_finding(severity="CRITICAL"),
            make_finding(severity="HIGH"),
            make_finding(severity="LOW"),
        ]
        report = ComplianceReport(
            verdict="FAIL",
            summary="test",
            findings=findings,
        )
        assert len(report.critical_findings) == 1
        assert len(report.high_findings) == 1


# ---------------------------------------------------------------------------
# PRReviewer / _render_comment tests
# ---------------------------------------------------------------------------

class TestRenderComment:
    def test_pass_verdict_in_output(self):
        report = make_compliance_report("PASS")
        md = _render_comment(report, pr_id=42)
        assert "PASS" in md
        assert "✅" in md

    def test_fail_verdict_in_output(self):
        report = make_compliance_report("FAIL", findings=[make_finding()])
        md = _render_comment(report, pr_id=42)
        assert "FAIL" in md
        assert "❌" in md

    def test_findings_rendered(self):
        findings = [make_finding(rule="approved-base-image", file="pipeline.yml")]
        report = make_compliance_report("FAIL", findings=findings)
        md = _render_comment(report, pr_id=1)
        assert "approved-base-image" in md
        assert "pipeline.yml" in md
        assert "Unapproved Docker base image detected" in md

    def test_compliant_items_rendered(self):
        report = make_compliance_report("PASS")
        md = _render_comment(report, pr_id=1)
        assert "Compliant Items" in md
        assert "Approved base image used" in md

    def test_severity_emoji_included(self):
        findings = [make_finding(severity="CRITICAL")]
        report = make_compliance_report("FAIL", findings=findings)
        md = _render_comment(report, pr_id=1)
        assert "🔴" in md

    def test_recommendation_in_output(self):
        findings = [make_finding()]
        report = make_compliance_report("FAIL", findings=findings)
        md = _render_comment(report, pr_id=1)
        assert "ubuntu-22.04" in md


class TestPRReviewer:
    def test_raises_when_repo_id_missing(self):
        mock_ado = MagicMock()
        reviewer = PRReviewer(ado_client=mock_ado)
        reviewer.repo_id = ""
        report = make_compliance_report("PASS")
        with pytest.raises(EnvironmentError, match="ADO_REPOSITORY_ID"):
            reviewer.review(pr_id=1, report=report, repo_id="")

    def test_pass_sets_succeeded_status(self):
        mock_ado = MagicMock()
        mock_ado.post_pr_comment.return_value = {"id": 101}
        mock_ado.update_pr_status.return_value = {}

        reviewer = PRReviewer(ado_client=mock_ado)
        report = make_compliance_report("PASS")
        result = reviewer.review(pr_id=5, report=report, repo_id="my-repo")

        assert result.verdict == "PASS"
        assert result.status_state == "succeeded"
        mock_ado.update_pr_status.assert_called_once()
        call_args = mock_ado.update_pr_status.call_args
        assert call_args.kwargs.get("state") == "succeeded" or call_args[1].get("state") == "succeeded" or "succeeded" in str(call_args)

    def test_fail_sets_failed_status(self):
        mock_ado = MagicMock()
        mock_ado.post_pr_comment.return_value = {"id": 202}
        mock_ado.update_pr_status.return_value = {}

        reviewer = PRReviewer(ado_client=mock_ado)
        report = make_compliance_report("FAIL", findings=[make_finding()])
        result = reviewer.review(pr_id=7, report=report, repo_id="my-repo")

        assert result.verdict == "FAIL"
        assert result.status_state == "failed"

    def test_comment_thread_id_captured(self):
        mock_ado = MagicMock()
        mock_ado.post_pr_comment.return_value = {"id": 999}
        mock_ado.update_pr_status.return_value = {}

        reviewer = PRReviewer(ado_client=mock_ado)
        result = reviewer.review(
            pr_id=3, report=make_compliance_report("PASS"), repo_id="repo-x"
        )
        assert result.comment_thread_id == 999
