# Scenario 2 Design — AI PR Compliance

## Problem Statement

Engineering teams maintain standards documents in Confluence (pipeline patterns, security requirements, naming conventions, approved base images, etc.). Ensuring that every pull request complies with these standards is currently a manual, error-prone process. Reviewers may not be aware of the latest standards updates, and compliance checks are inconsistently applied.

## Solution

An AI agent that:
1. Pulls the latest engineering standards from Confluence automatically.
2. For each PR, fetches the changed files (YAML, Python, config).
3. Uses GPT-4o to evaluate the files against the standards.
4. Posts a structured compliance report as a PR comment.
5. Sets a custom ADO PR status that is required by branch policy — **blocking the PR from merging on FAIL**.

---

## Component Design

### ConfluenceFetcher

- Authenticates using HTTP Basic auth with an API token.
- Fetches pages from one or more Confluence spaces: `GET /rest/api/content?spaceKey=X&expand=body.storage`.
- Supports fetching specific pages by ID for always-include standards.
- Strips HTML from page bodies to produce clean plain text for GPT context.
- De-duplicates documents across spaces to avoid feeding the same content twice.

**Key design decisions:**
- Plain text extraction (not raw HTML) keeps the GPT context clean and token-efficient.
- Supports multiple space keys to cover different teams' standards.
- Extra page IDs allow pinning critical standards that may not be in a monitored space.

### ComplianceChecker

- Assembles a standards context (truncated to ~12,000 chars to stay within context limits).
- Assembles a files context (each file path + content, truncated to 6,000 chars per file).
- Sends to GPT-4o with a system prompt that defines the reviewer role and response schema.
- Parses JSON response into a `ComplianceReport` with a `PASS`/`FAIL` verdict and per-file findings.
- Each finding includes: file path, severity, rule name, description, line hint, recommendation.

**Compliance verdict logic:**
- **FAIL** if any CRITICAL or HIGH severity finding is present.
- **PASS** if only MEDIUM, LOW, or INFO findings exist.

**Prompt strategy:**
- System prompt enforces JSON-only output with a strict schema.
- Temperature is set to 0.1 for maximum consistency.
- The GPT is instructed to also call out compliant items (positive reinforcement).

### PRReviewer

- Renders the `ComplianceReport` as a Markdown comment with severity emoji, finding details, and recommendations.
- Posts the comment as a thread: `POST /git/repositories/{repo}/pullrequests/{id}/threads`.
- Sets a custom PR status: `POST /git/repositories/{repo}/pullrequests/{id}/statuses`.
  - Status context: `ai-devsecops/ai-pr-compliance`
  - State: `succeeded` (PASS) or `failed` (FAIL)
- The branch policy in ADO requires this status check — making it a hard gate.

### Orchestrator (webhook server mode)

- FastAPI application with two endpoints:
  - `POST /webhook/pr-created`
  - `POST /webhook/pr-updated`
- Parses the ADO Service Hook payload to extract `pullRequestId` and `repository.id`.
- Delegates to `run_for_pr()` which runs the full pipeline.
- Returns the compliance result as JSON.

---

## Data Models

```python
StandardsDocument:
  page_id, title, space_key, url, content,
  last_modified, labels

ComplianceFinding:
  file, severity, rule, description,
  line_hint, recommendation

ComplianceReport:
  verdict, summary, findings, compliant_items,
  is_passing, critical_findings, high_findings
```

---

## Branch Policy Configuration

To enforce compliance as a merge gate:

1. Navigate to ADO → Repos → Branches → `main` → Branch Policies.
2. Add a **Status Check** required policy.
3. Configure:
   - **Status name**: `ai-pr-compliance`
   - **Status genre**: `ai-devsecops`
4. Set as **Required** (not optional).

When a PR fails compliance, the merge button is disabled and the PR shows a failed status badge. The PR author can see the detailed findings in the comment thread.

---

## File Type Selection

Only text-based files are reviewed. The current allowlist:

```python
TEXT_EXTENSIONS = {
    ".yml", ".yaml",  # Pipeline and config YAML
    ".py",            # Python source
    ".json",          # JSON config
    ".tf",            # Terraform
    ".sh",            # Shell scripts
    ".md",            # Documentation
    ".txt",           # Text files
    ".cfg", ".ini",   # Configuration files
    ".toml",          # TOML config
}
```

Binary files (images, compiled artifacts) are skipped.

---

## Error Handling

| Failure | Behaviour |
|---|---|
| Confluence API 401 | Fail fast; log error with remediation hint |
| Confluence API 429 | Retry with backoff (3 attempts) |
| GPT returns invalid JSON | Treat as FAIL with a "review-error" finding |
| File content fetch fails | Log warning; skip file (review what's available) |
| ADO PR comment post fails | Log error; do not fail the pipeline (best-effort) |
| ADO status update fails | Log error; raise (this is required for the branch gate) |

---

## Privacy and Token Efficiency

- Standards are truncated to `MAX_STANDARDS_CHARS` (12,000) before sending to GPT.
- Individual files are truncated to `MAX_FILE_CHARS` (6,000) per file.
- Confluence HTML is stripped before sending to GPT — no raw markup is transmitted.
- No build logs, PR descriptions, or commit messages are sent to the LLM by default.
