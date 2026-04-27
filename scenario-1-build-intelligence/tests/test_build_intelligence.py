"""
Unit tests for Scenario 1 — AI Build Intelligence.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scenario-1 directory is at sys.path[0] (not scenario-2's agent)
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

from shared.ado_client import BuildFailure
from agent.failure_pattern_miner import FailurePatternMiner, FailurePattern
from agent.root_cause_clusterer import RootCauseClusterer, RootCauseFinding
from agent.wiki_publisher import render_wiki_page, WikiPublisher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_failure(
    build_id: int = 1,
    pipeline_name: str = "ci-pipeline",
    pipeline_id: int = 10,
    branch: str = "main",
    error_messages: list[str] | None = None,
    failed_task_name: str = "Run Tests",
) -> BuildFailure:
    return BuildFailure(
        build_id=build_id,
        pipeline_name=pipeline_name,
        pipeline_id=pipeline_id,
        branch=branch,
        start_time="2024-01-01T10:00:00Z",
        finish_time="2024-01-01T10:05:00Z",
        reason="manual",
        requested_by="developer@example.com",
        failed_tasks=[{"name": failed_task_name, "result": "failed"}],
        error_messages=error_messages or ["Error: connection refused on port 5432"],
    )


# ---------------------------------------------------------------------------
# FailurePatternMiner tests
# ---------------------------------------------------------------------------

class TestFailurePatternMiner:
    def test_empty_input_returns_empty(self):
        miner = FailurePatternMiner()
        result = miner.mine([])
        assert result == []

    def test_single_failure_forms_pattern(self):
        miner = FailurePatternMiner(min_cluster_size=1)
        failures = [make_failure(build_id=1)]
        patterns = miner.mine(failures)
        assert len(patterns) == 1
        assert patterns[0].count == 1

    def test_similar_failures_grouped(self):
        miner = FailurePatternMiner(min_cluster_size=1)
        failures = [
            make_failure(build_id=i, error_messages=["Error: connection refused on port 5432"])
            for i in range(1, 4)
        ]
        patterns = miner.mine(failures)
        # All three have the same task + error prefix → single pattern
        assert len(patterns) == 1
        assert patterns[0].count == 3

    def test_different_errors_form_separate_patterns(self):
        miner = FailurePatternMiner(min_cluster_size=1)
        failures = [
            make_failure(build_id=1, error_messages=["Error: connection refused"]),
            make_failure(build_id=2, error_messages=["Error: file not found"]),
            make_failure(build_id=3, error_messages=["Error: file not found"]),
        ]
        patterns = miner.mine(failures)
        assert len(patterns) == 2

    def test_min_cluster_size_filters_singletons(self):
        miner = FailurePatternMiner(min_cluster_size=2)
        failures = [make_failure(build_id=1, error_messages=["unique error XYZ"])]
        patterns = miner.mine(failures)
        assert patterns == []

    def test_patterns_sorted_by_count_desc(self):
        miner = FailurePatternMiner(min_cluster_size=1)
        failures = (
            [make_failure(build_id=i, error_messages=["Error A"]) for i in range(1, 4)]
            + [make_failure(build_id=i + 10, error_messages=["Error B"]) for i in range(1, 2)]
        )
        patterns = miner.mine(failures)
        counts = [p.count for p in patterns]
        assert counts == sorted(counts, reverse=True)

    def test_pipeline_names_and_branches_collected(self):
        miner = FailurePatternMiner(min_cluster_size=1)
        failures = [
            make_failure(build_id=1, pipeline_name="pipe-A", branch="main"),
            make_failure(build_id=2, pipeline_name="pipe-B", branch="feature/x"),
        ]
        # Two different patterns (different errors by default unique build_id doesn't change key)
        # Force same error so they group
        for f in failures:
            f.error_messages = ["same error message here"]
        patterns = miner.mine(failures)
        assert len(patterns) == 1
        assert "pipe-A" in patterns[0].pipeline_names
        assert "pipe-B" in patterns[0].pipeline_names

    def test_volatile_tokens_normalised(self):
        """GUIDs and timestamps should not create spurious distinct patterns."""
        miner = FailurePatternMiner(min_cluster_size=1)
        failures = [
            make_failure(
                build_id=1,
                error_messages=["Error: GUID 550e8400-e29b-41d4-a716-446655440000 invalid"],
            ),
            make_failure(
                build_id=2,
                error_messages=["Error: GUID 11111111-2222-3333-4444-555555555555 invalid"],
            ),
        ]
        patterns = miner.mine(failures)
        # Both should normalise to the same pattern
        assert len(patterns) == 1
        assert patterns[0].count == 2


# ---------------------------------------------------------------------------
# RootCauseClusterer tests
# ---------------------------------------------------------------------------

class TestRootCauseClusterer:
    def test_empty_patterns_returns_empty(self):
        clusterer = RootCauseClusterer(openai_client=MagicMock())
        result = clusterer.analyse([])
        assert result == []

    def test_returns_finding_per_pattern(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = (
            '{"title": "DB Connection Failure", "severity": "HIGH", '
            '"root_cause": "Database unreachable.", '
            '"remediation_steps": ["Check DB connectivity."], '
            '"affected_pipelines": ["ci-pipeline"], '
            '"affected_branches": ["main"]}'
        )
        failures = [make_failure(build_id=i) for i in range(1, 4)]
        pattern = FailurePattern(
            pattern_key="run-tests::error: connection refused",
            failures=failures,
            representative_errors=["Error: connection refused on port 5432"],
        )

        clusterer = RootCauseClusterer(openai_client=mock_client)
        findings = clusterer.analyse([pattern])

        assert len(findings) == 1
        finding = findings[0]
        assert finding.title == "DB Connection Failure"
        assert finding.severity == "HIGH"
        assert "Database unreachable" in finding.root_cause
        assert len(finding.remediation_steps) == 1

    def test_invalid_json_uses_fallback(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = "This is not JSON"
        failures = [make_failure(build_id=1)]
        pattern = FailurePattern(
            pattern_key="unknown-task::no-error",
            failures=failures,
            representative_errors=[],
        )

        clusterer = RootCauseClusterer(openai_client=mock_client)
        findings = clusterer.analyse([pattern])

        assert len(findings) == 1
        # Fallback should set a default severity
        assert findings[0].severity == "MEDIUM"

    def test_exception_in_pattern_does_not_crash(self):
        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("API unreachable")
        failures = [make_failure(build_id=1)]
        pattern = FailurePattern(
            pattern_key="test::error",
            failures=failures,
            representative_errors=[],
        )
        clusterer = RootCauseClusterer(openai_client=mock_client)
        # Should not raise — failed patterns are skipped
        findings = clusterer.analyse([pattern])
        assert findings == []


# ---------------------------------------------------------------------------
# WikiPublisher / render_wiki_page tests
# ---------------------------------------------------------------------------

def _make_finding(title: str = "Test Failure", severity: str = "HIGH", count: int = 3) -> RootCauseFinding:
    failures = [make_failure(build_id=i) for i in range(count)]
    pattern = FailurePattern(
        pattern_key="task::error",
        failures=failures,
        representative_errors=["Some error"],
    )
    return RootCauseFinding(
        pattern=pattern,
        raw_json={
            "title": title,
            "severity": severity,
            "root_cause": "Root cause explanation.",
            "remediation_steps": ["Step 1", "Step 2"],
            "affected_pipelines": ["ci-pipeline"],
            "affected_branches": ["main"],
        },
    )


class TestRenderWikiPage:
    def test_empty_findings_shows_no_patterns_message(self):
        content = render_wiki_page([])
        assert "No failure patterns" in content

    def test_findings_rendered_with_title(self):
        findings = [_make_finding("Database Connection Error")]
        content = render_wiki_page(findings)
        assert "Database Connection Error" in content

    def test_severity_emoji_present(self):
        findings = [_make_finding(severity="CRITICAL")]
        content = render_wiki_page(findings)
        assert "🔴" in content

    def test_remediation_steps_rendered(self):
        findings = [_make_finding()]
        content = render_wiki_page(findings)
        assert "Step 1" in content
        assert "Step 2" in content

    def test_occurrence_count_in_output(self):
        findings = [_make_finding(count=5)]
        content = render_wiki_page(findings)
        assert "5" in content

    def test_generated_at_timestamp_in_header(self):
        findings = [_make_finding()]
        content = render_wiki_page(findings, generated_at="2024-06-01T00:00:00Z")
        assert "2024-06-01T00:00:00Z" in content

    def test_multiple_findings_all_rendered(self):
        findings = [
            _make_finding("Error A", "HIGH", 2),
            _make_finding("Error B", "LOW", 1),
        ]
        content = render_wiki_page(findings)
        assert "Error A" in content
        assert "Error B" in content


class TestWikiPublisher:
    def test_raises_when_wiki_id_not_set(self, monkeypatch):
        monkeypatch.delenv("ADO_WIKI_ID", raising=False)
        publisher = WikiPublisher(ado_client=MagicMock())
        publisher.wiki_id = ""
        with pytest.raises(EnvironmentError):
            publisher.publish([_make_finding()])

    def test_calls_ado_upsert(self, monkeypatch):
        monkeypatch.setenv("ADO_WIKI_ID", "my-wiki")
        mock_ado = MagicMock()
        mock_ado.get_wiki_page_version.return_value = None
        mock_ado.upsert_wiki_page.return_value = {}

        publisher = WikiPublisher(ado_client=mock_ado)
        publisher.wiki_id = "my-wiki"
        publisher.wiki_path = "/Test/Path"
        publisher.publish([_make_finding()])

        mock_ado.upsert_wiki_page.assert_called_once()
        call_kwargs = mock_ado.upsert_wiki_page.call_args
        assert "my-wiki" in str(call_kwargs)
