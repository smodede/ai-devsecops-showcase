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
1. Engineering standards extracted from Confluence — these are the ONLY rules you must evaluate against.
2. The content of files from a pull request (pipeline YAML, source code, config).
3. Pull request context (source branch, target branch, promotion path).

Your task:
- Evaluate ONLY against the rules explicitly defined in the provided Confluence standards.
- Do NOT raise findings for general code quality, style, logging verbosity, or best practices
  that are not explicitly listed in the standards.
- Each finding's "rule" field MUST reference a specific standard from the Confluence document by name.
- Each finding's "severity" field MUST use the severity level from the Compliance Summary table at the
  bottom of the standards document — do NOT assign your own severity judgement.
- Raise findings for the PR promotion path (branching strategy) based on the PR context provided.
- Call out what is correctly implemented relative to the standards (compliant_items).
- Assign a final verdict: PASS or FAIL.
  - FAIL if any CRITICAL or HIGH severity violations are found.
  - PASS otherwise (MEDIUM/LOW/INFO are advisory only).

Respond with valid JSON matching this exact schema:
{
  "verdict": "PASS | FAIL",
  "summary": "One-sentence overall assessment",
  "findings": [
    {
      "file": "path/to/file.yml",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW | INFO",
      "rule": "Exact rule name as stated in the Confluence standards",
      "description": "What is wrong and which standard it violates",
      "line_hint": "optional: line number or snippet context",
      "recommendation": "Concrete fix aligned with the standard"
    }
  ],
  "compliant_items": [
    "Description of what correctly satisfies a specific standard"
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
        pr_context: dict | None = None,
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

        pr_context_section = ""
        if pr_context:
            source = pr_context.get("source_branch", "unknown")
            target = pr_context.get("target_branch", "unknown")
            pr_id = pr_context.get("pr_id", "")
            pr_context_section = f"""\
## Pull Request Context

- **PR ID:** {pr_id}
- **Source branch:** `{source}`
- **Target branch:** `{target}`
- **Promotion path of this PR:** `{source}` -> `{target}`

IMPORTANT: Evaluate whether this promotion path complies with the branching strategy defined in the standards.

---

"""

        user_prompt = f"""\
## Engineering Standards

{standards_context}

---

{pr_context_section}## Pull Request Files Under Review

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

        raw_response = self._client.chat(messages, temperature=0.0, max_tokens=3000)
        logger.debug("GPT compliance response: %s", truncate(raw_response, 400))

        # Strip markdown code fences GPT sometimes wraps the JSON in
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]  # remove opening ```json line
            cleaned = cleaned.rsplit("```", 1)[0]  # remove closing ```
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
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
