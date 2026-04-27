"""
Root Cause Clusterer — Scenario 1.

Takes :class:`FailurePattern` objects produced by the pattern miner and
uses GPT (via Azure OpenAI) to:
  1. Identify the root cause for each pattern.
  2. Suggest concrete remediation steps.
  3. Produce a structured analysis ready for Wiki publishing.
"""

from __future__ import annotations

import json
import logging

from shared.azure_openai_client import AzureOpenAIClient
from shared.utils import truncate

from .failure_pattern_miner import FailurePattern

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior DevOps engineer and build reliability expert.
You will be given data about repeated Azure DevOps pipeline failures.
Your job is to:
1. Identify the most likely root cause.
2. Provide a severity rating: CRITICAL | HIGH | MEDIUM | LOW.
3. List 3–5 concrete, actionable remediation steps.
4. Suggest a short title (≤ 10 words) for this failure pattern.

Always respond with valid JSON matching this exact schema:
{
  "title": "string",
  "severity": "CRITICAL | HIGH | MEDIUM | LOW",
  "root_cause": "string (2–4 sentences)",
  "remediation_steps": ["step 1", "step 2", ...],
  "affected_pipelines": ["pipeline name", ...],
  "affected_branches": ["branch name", ...]
}
Do not include any text outside the JSON object.
"""


def _build_user_prompt(pattern: FailurePattern) -> str:
    errors_section = "\n".join(f"  - {e}" for e in pattern.representative_errors) or "  (none captured)"
    return f"""\
## Failure Pattern: `{pattern.pattern_key}`

**Occurrence count:** {pattern.count}
**Affected pipelines:** {', '.join(pattern.pipeline_names) or 'unknown'}
**Affected branches:** {', '.join(pattern.branches) or 'unknown'}

**Representative error messages:**
{errors_section}

Analyse this failure pattern and return the JSON response as instructed.
"""


class RootCauseFinding:
    """Holds GPT's analysis of a single failure pattern."""

    def __init__(self, pattern: FailurePattern, raw_json: dict) -> None:
        self.pattern = pattern
        self.title: str = raw_json.get("title", pattern.pattern_key)
        self.severity: str = raw_json.get("severity", "MEDIUM")
        self.root_cause: str = raw_json.get("root_cause", "Unknown root cause.")
        self.remediation_steps: list[str] = raw_json.get("remediation_steps", [])
        self.affected_pipelines: list[str] = raw_json.get(
            "affected_pipelines", pattern.pipeline_names
        )
        self.affected_branches: list[str] = raw_json.get(
            "affected_branches", pattern.branches
        )


class RootCauseClusterer:
    """
    Uses Azure OpenAI to analyse failure patterns and produce
    structured root cause findings.
    """

    def __init__(self, openai_client: AzureOpenAIClient | None = None) -> None:
        self._client = openai_client or AzureOpenAIClient()

    def analyse(self, patterns: list[FailurePattern]) -> list[RootCauseFinding]:
        """
        Analyse each pattern and return a list of findings.

        Args:
            patterns: Heuristically mined failure patterns.

        Returns:
            List of :class:`RootCauseFinding` objects, one per pattern.
        """
        if not patterns:
            logger.info("No patterns to analyse.")
            return []

        findings: list[RootCauseFinding] = []
        for i, pattern in enumerate(patterns, 1):
            logger.info(
                "Analysing pattern %d/%d: %s (count=%d)",
                i, len(patterns), pattern.pattern_key, pattern.count,
            )
            try:
                finding = self._analyse_pattern(pattern)
                findings.append(finding)
            except Exception:
                logger.exception("Failed to analyse pattern '%s'", pattern.pattern_key)

        logger.info("Produced %d root cause findings", len(findings))
        return findings

    def _analyse_pattern(self, pattern: FailurePattern) -> RootCauseFinding:
        user_prompt = _build_user_prompt(pattern)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        raw_response = self._client.chat(messages, temperature=0.2)
        logger.debug("GPT raw response for pattern '%s': %s", pattern.pattern_key, truncate(raw_response, 300))

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning(
                "GPT did not return valid JSON for pattern '%s'; using fallback.",
                pattern.pattern_key,
            )
            parsed = {
                "title": pattern.pattern_key,
                "severity": "MEDIUM",
                "root_cause": raw_response[:500],
                "remediation_steps": ["Review the error messages manually."],
            }

        return RootCauseFinding(pattern, parsed)
