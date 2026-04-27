# Scenario 1 Design — AI Build Intelligence

## Problem Statement

Engineering teams running Azure DevOps pipelines accumulate hundreds of failed builds over time. Investigating each failure manually is time-consuming. Repeated failures with the same root cause are often fixed independently by different team members, wasting effort. There is no consolidated view of which failure patterns are most impactful.

## Solution

An AI agent that:
1. Periodically fetches all failed pipeline runs from Azure DevOps.
2. Groups failures into patterns using lightweight heuristics.
3. Uses GPT-4o to identify root causes and generate actionable remediation steps.
4. Publishes a structured, ranked report to an Azure DevOps Wiki page — automatically, with no human intervention.

---

## Component Design

### BuildFailureFetcher

- Calls `GET /build/builds?resultFilter=failed&$top=N` to retrieve recent failures.
- For each failure, fetches the build timeline to extract:
  - Names of failed tasks
  - Error messages from timeline issue records
- Produces a list of `BuildFailure` dataclass objects.

**Key design decisions:**
- Uses the ADO REST API v7.1 directly (not the Python SDK) to minimise dependency footprint.
- Timeline enrichment is best-effort: individual timeline fetch failures are logged and skipped.

### FailurePatternMiner

- Groups failures by `(normalised_task_name, normalised_error_prefix)`.
- Normalisation strips GUIDs, timestamps, numeric IDs, and file paths — ensuring that semantically identical errors from different builds are grouped together.
- Returns `FailurePattern` objects sorted by occurrence count (most frequent first).
- `min_cluster_size` parameter (default 2) filters out one-off failures.

**Key design decisions:**
- Heuristic pre-grouping before GPT call: reduces the number of GPT requests (one per pattern, not one per failure).
- Simple regex-based normalisation is fast and deterministic.

### RootCauseClusterer

- Sends each `FailurePattern` to GPT-4o with a structured prompt.
- Prompt requests a JSON response with title, severity, root cause, remediation steps, and affected pipelines/branches.
- Parses JSON response; falls back to a graceful default if JSON is invalid.
- Exception handling: a failed analysis for one pattern does not abort the whole cycle.

**Prompt strategy:**
- System prompt establishes GPT as a "senior DevOps engineer".
- User prompt provides pattern data in a structured Markdown format.
- Temperature is set to 0.2 for consistent, deterministic output.
- JSON-only response is enforced in the system prompt.

### WikiPublisher

- Renders findings to a Markdown page with:
  - Table of contents
  - Per-finding sections with severity emoji, occurrence count, pipelines, branches, root cause, and numbered remediation steps
- Upserts the Wiki page using `PUT /wiki/wikis/{id}/pages`:
  - First checks if the page exists (to get its ETag for optimistic concurrency)
  - Creates or updates accordingly

---

## Data Models

```python
BuildFailure:
  build_id, pipeline_name, pipeline_id, branch,
  start_time, finish_time, reason, requested_by,
  failed_tasks, error_messages

FailurePattern:
  pattern_key, failures, representative_errors,
  count, pipeline_names, branches

RootCauseFinding:
  pattern, title, severity, root_cause,
  remediation_steps, affected_pipelines, affected_branches
```

---

## Pipeline Schedule

```
Trigger: daily cron at 06:00 UTC
Steps:
  1. Set up Python 3.11
  2. Install requirements
  3. Run unit tests
  4. Execute orchestrator (fetch → mine → analyse → publish)
  5. Publish test results artifact
```

Manual trigger: any ADO user can run the pipeline with custom parameters (pipeline IDs, date range, dry-run mode).

---

## Error Handling

| Failure | Behaviour |
|---|---|
| ADO API returns 429 | Retry with backoff (3 attempts) |
| ADO API returns 404 for timeline | Failure skipped; logged as warning |
| GPT returns invalid JSON | Fallback finding created; logged as warning |
| GPT call raises exception | Pattern skipped; logged as error |
| Wiki page does not exist | Page is created (no ETag required) |
| Wiki API returns 412 Conflict | ETag mismatch; re-fetch and retry |
