"""
Compliance Checker — Scenario 2.

Evaluates pipeline YAML and source code against engineering standards
fetched from Confluence, returning structured compliance findings.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from shared.azure_openai_client import AzureOpenAIClient
from shared.utils import truncate

from .confluence_fetcher import StandardsDocument

logger = logging.getLogger(__name__)

_MAX_STANDARDS_CHARS = 12_000  # Truncate standards context to stay within token limits
_MAX_FILE_CHARS = 6_000        # Truncate individual file content

_SYSTEM_PROMPT = """\
You are a senior DevSecOps compliance reviewer.

You will receive:
1. Engineering standards and policies extracted from Confluence.
2. The content of one or more files from a pull request (pipeline YAML, source code, config).

Your task:
- Review each file against the provided standards.
- For each violation or concern, produce a finding.
- Also explicitly call out what the file gets RIGHT (compliant sections).
- Assign a final verdict: PASS or FAIL.
  - FAIL if any CRITICAL or HIGH severity violations are found.
  - PASS otherwise (MEDIUM/LOW are advisory only).

Respond with valid JSON matching this exact schema:
{
  "verdict": "PASS | FAIL",
  "summary": "One-sentence overall assessment",
  "findings": [
    {
      "file": "path/to/file.yml",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW | INFO",
      "rule": "Short rule name from the standards",
      "description": "What is wrong or noteworthy",
      "line_hint": "optional: line number or snippet context",
      "recommendation": "Concrete fix"
    }
  ],
  "compliant_items": [
    "Description of what is correctly implemented"
  ]
}
Do not include any text outside the JSON object.
"""


@dataclass
class ComplianceFinding:
    """A single compliance finding for a file in the PR."""

    file: str
    severity: str
    rule: str
    description: str
    line_hint: str = ""
    recommendation: str = ""


@dataclass
class ComplianceReport:
    """Aggregated compliance report for all files in a PR."""

    verdict: str  # PASS | FAIL
    summary: str
    findings: list[ComplianceFinding] = field(default_factory=list)
    compliant_items: list[str] = field(default_factory=list)

    @property
    def is_passing(self) -> bool:
        return self.verdict == "PASS"

    @property
    def critical_findings(self) -> list[ComplianceFinding]:
        return [f for f in self.findings if f.severity == "CRITICAL"]

    @property
    def high_findings(self) -> list[ComplianceFinding]:
        return [f for f in self.findings if f.severity == "HIGH"]


def _build_standards_context(standards: list[StandardsDocument]) -> str:
    """Assemble standards documents into a single truncated context string."""
    parts = []
    total = 0
    for doc in standards:
        chunk = f"### {doc.title}\n\n{doc.content}\n\n"
        if total + len(chunk) > _MAX_STANDARDS_CHARS:
            remaining = _MAX_STANDARDS_CHARS - total
            if remaining > 200:
                parts.append(chunk[:remaining] + "\n[... truncated ...]")
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts)


def _build_files_context(files: dict[str, str]) -> str:
    """Format PR files into a review context string."""
    parts = []
    for path, content in files.items():
        safe_content = truncate(content, _MAX_FILE_CHARS)
        parts.append(f"### File: `{path}`\n\n```\n{safe_content}\n```\n")
    return "\n".join(parts)


class ComplianceChecker:
    """
    Uses Azure OpenAI to check PR files against Confluence-sourced standards.
    """

    def __init__(self, openai_client: AzureOpenAIClient | None = None) -> None:
        self._client = openai_client or AzureOpenAIClient()

    def check(
        self,
        files: dict[str, str],
        standards: list[StandardsDocument],
    ) -> ComplianceReport:
        """
        Check the given files against the provided standards.

        Args:
            files: Dict mapping file paths to their text content.
            standards: Confluence standards documents to evaluate against.

        Returns:
            :class:`ComplianceReport` with verdict and findings.
        """
        if not files:
            logger.info("No files provided for compliance check.")
            return ComplianceReport(verdict="PASS", summary="No files to review.")

        standards_context = _build_standards_context(standards)
        files_context = _build_files_context(files)

        user_prompt = f"""\
## Engineering Standards

{standards_context}

---

## Pull Request Files Under Review

{files_context}

---

Review the files above against the engineering standards and return the compliance JSON.
"""

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "Running compliance check (files=%d, standards=%d)",
            len(files),
            len(standards),
        )

        raw_response = self._client.chat(messages, temperature=0.1, max_tokens=3000)
        logger.debug("GPT compliance response: %s", truncate(raw_response, 400))

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("GPT did not return valid JSON; treating as FAIL.")
            return ComplianceReport(
                verdict="FAIL",
                summary="Compliance check returned unparseable response.",
                findings=[
                    ComplianceFinding(
                        file="(unknown)",
                        severity="HIGH",
                        rule="review-error",
                        description="AI compliance check failed to produce a valid JSON response.",
                        recommendation="Re-run the compliance check or review manually.",
                    )
                ],
            )

        findings = [
            ComplianceFinding(
                file=f.get("file", ""),
                severity=f.get("severity", "MEDIUM"),
                rule=f.get("rule", ""),
                description=f.get("description", ""),
                line_hint=f.get("line_hint", ""),
                recommendation=f.get("recommendation", ""),
            )
            for f in parsed.get("findings", [])
        ]

        report = ComplianceReport(
            verdict=parsed.get("verdict", "FAIL"),
            summary=parsed.get("summary", ""),
            findings=findings,
            compliant_items=parsed.get("compliant_items", []),
        )

        logger.info(
            "Compliance check complete: verdict=%s, findings=%d (critical=%d, high=%d)",
            report.verdict,
            len(report.findings),
            len(report.critical_findings),
            len(report.high_findings),
        )
        return report
