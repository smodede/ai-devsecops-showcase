# Scenario 1 — AI Build Intelligence: Component Reference

This document provides a detailed technical reference for every component in the AI Build Intelligence scenario. It is intended for developers who want to understand, extend, or debug the system.

---

## Overview

AI Build Intelligence is an automated agent that:

1. Periodically fetches failed Azure DevOps pipeline runs
2. Groups them into failure patterns using lightweight heuristics
3. Sends each pattern to GPT-4o for root cause analysis
4. Publishes a ranked remediation report to an Azure DevOps Wiki page

```
Azure DevOps Builds
       │
       ▼  GET /build/builds?resultFilter=failed
┌──────────────────────┐
│  BuildFailureFetcher │
└──────────┬───────────┘
           │  list[BuildFailure]
           ▼  group by (task_name, error_prefix)
┌──────────────────────┐
│  FailurePatternMiner │
└──────────┬───────────┘
           │  list[FailurePattern]
           ▼  POST /openai/deployments/gpt-4o/chat/completions
┌──────────────────────┐
│  RootCauseClusterer  │
└──────────┬───────────┘
           │  list[RootCauseFinding]
           ▼  PUT /wiki/wikis/{id}/pages?path=...
┌──────────────────────┐
│    WikiPublisher     │
└──────────────────────┘
           │
           ▼
  ADO Wiki page with ranked
  remediation findings
```

---

## Data Models

Before examining each component it helps to understand the data structures that flow between them.

### `BuildFailure` — `shared/ado_client.py`

| Attribute | Detail |
|---|---|
| **Description** | Represents a single failed ADO pipeline run, enriched with task-level error detail extracted from the build timeline. Produced by `BuildFailureFetcher` and consumed by `FailurePatternMiner`. |
| **Defined in** | `shared/ado_client.py` — shared across both scenarios |
| **Python construct** | `@dataclass` |
| **Technologies** | Azure DevOps REST API v7.1 (`/build/builds`, `/build/builds/{id}/timeline`), Python `dataclasses`, `requests` |
| **Lifetime** | In-memory only; not persisted between pipeline runs |

#### Fields

| Field | Type | Description |
|---|---|---|
| `build_id` | `int` | ADO build run ID |
| `pipeline_name` | `str` | Human-readable pipeline name |
| `pipeline_id` | `int` | ADO pipeline definition ID |
| `branch` | `str` | Source branch (e.g. `refs/heads/main`) |
| `start_time` | `str` | ISO 8601 run start timestamp |
| `finish_time` | `str` | ISO 8601 run end timestamp |
| `reason` | `str` | Trigger reason (`manual`, `schedule`, etc.) |
| `requested_by` | `str` | Identity that triggered the run |
| `failed_tasks` | `list[dict]` | Timeline records of failed tasks (`name`, `result`) |
| `error_messages` | `list[str]` | Error message strings extracted from timeline issues |
| `logs_url` | `str` | URL to the build log (populated when available) |

### `FailurePattern` — `agent/failure_pattern_miner.py`

| Attribute | Detail |
|---|---|
| **Description** | A named cluster of `BuildFailure` records that share the same normalised error signature. Built by heuristic bucketing — no ML required. Consumed by `RootCauseClusterer` to produce one GPT call per pattern rather than one per failure. |
| **Defined in** | `scenario-1-build-intelligence/agent/failure_pattern_miner.py` |
| **Python construct** | `@dataclass` with computed `@property` accessors |
| **Technologies** | Python `dataclasses`, `re` (built-in regex) — no external dependencies |
| **Lifetime** | In-memory only; not persisted between pipeline runs |

#### Fields

| Field / Property | Type | Description |
|---|---|---|
| `pattern_key` | `str` | Composite key: `"{task_name}::{normalised_error_prefix}"` |
| `failures` | `list[BuildFailure]` | All failures in this cluster |
| `representative_errors` | `list[str]` | Up to 5 unique, normalised error messages |
| `count` *(property)* | `int` | Number of failures in the cluster |
| `pipeline_names` *(property)* | `list[str]` | Sorted unique pipeline names |
| `branches` *(property)* | `list[str]` | Sorted unique branch names |

### `RootCauseFinding` — `agent/root_cause_clusterer.py`

| Attribute | Detail |
|---|---|
| **Description** | GPT-4o's structured root cause analysis of a `FailurePattern`. Contains a severity rating, a human-readable root cause explanation, and ordered remediation steps. Produced by `RootCauseClusterer` and consumed by `WikiPublisher`. |
| **Defined in** | `scenario-1-build-intelligence/agent/root_cause_clusterer.py` |
| **Python construct** | `@dataclass` |
| **Technologies** | Azure OpenAI (`gpt-4o` deployment), `openai` Python SDK, `json` (built-in) for structured response parsing |
| **Lifetime** | In-memory only; serialised to Markdown by `WikiPublisher` then discarded |

#### Fields

| Field | Type | Description |
|---|---|---|
| `pattern` | `FailurePattern` | The source pattern |
| `title` | `str` | Short human-readable title (≤ 10 words) |
| `severity` | `str` | `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` |
| `root_cause` | `str` | 2–4 sentence explanation |
| `remediation_steps` | `list[str]` | 3–5 actionable steps |
| `affected_pipelines` | `list[str]` | Pipeline names from GPT (falls back to pattern data) |
| `affected_branches` | `list[str]` | Branch names from GPT (falls back to pattern data) |

---

## Component 1 — BuildFailureFetcher

**File:** [`scenario-1-build-intelligence/agent/build_failure_fetcher.py`](../scenario-1-build-intelligence/agent/build_failure_fetcher.py)

### Responsibility

Queries the Azure DevOps REST API for failed pipeline runs and enriches each one with task-level failure details from the build timeline.

### How it works

1. Reads `ADO_PIPELINE_IDS` (comma-separated) and `MAX_BUILD_RUNS` from environment (or accepts them as arguments).
2. Calls `ADOClient.extract_build_failures()` which:
   - Fetches builds: `GET /{org}/{project}/_apis/build/builds?resultFilter=failed&$top=N`
   - Optionally filters to specific pipeline definition IDs
   - For each failed build, fetches its timeline: `GET /_apis/build/builds/{id}/timeline`
   - Extracts failed task records (`result == "failed"`) and their associated `issues[].message` error strings
3. Returns a `list[BuildFailure]`

### Key design choices

- **Timeline enrichment is best-effort**: if a timeline fetch fails (e.g. 404 for a deleted build), the failure is still included but with empty `failed_tasks`/`error_messages`, and a warning is logged.
- **No ADO Python SDK**: uses `requests` directly against the REST API to minimise dependency footprint and avoid SDK auth adapter complexity.
- **Retry adapter**: the underlying `ADOClient` mounts a `urllib3.Retry` adapter — 3 attempts, exponential backoff, triggers on `429` and `5xx` responses.

### Configuration

| Env var | Default | Description |
|---|---|---|
| `ADO_PIPELINE_IDS` | *(all)* | Comma-separated pipeline definition IDs to monitor |
| `MAX_BUILD_RUNS` | `100` | Maximum failed builds to retrieve per cycle |

---

## Component 2 — FailurePatternMiner

**File:** [`scenario-1-build-intelligence/agent/failure_pattern_miner.py`](../scenario-1-build-intelligence/agent/failure_pattern_miner.py)

### Responsibility

Groups raw `BuildFailure` records into clusters *before* calling GPT — ensuring one GPT request per *pattern*, not per *individual failure*. This keeps cost and latency low even when hundreds of failures exist.

### How it works

Each failure is mapped to a composite key:

```
pattern_key = "{task_name}::{normalised_error_prefix}"
```

**Task name** is derived from the first failed task in the timeline, lowercased and hyphenated:

```python
"Run Tests" → "run-tests"
```

**Error prefix** is the first 80 characters of the first error message, after normalisation:

```python
def _normalise_error(msg: str) -> str:
    msg = re.sub(r"[0-9a-f]{8}-...", "<GUID>", msg)       # Strip GUIDs
    msg = re.sub(r"\d{4}-\d{2}-\d{2}T...", "<TIMESTAMP>", msg)  # Strip timestamps
    msg = re.sub(r"(?:/[\w.\-]+)+", "<PATH>", msg)          # Strip file paths
    msg = re.sub(r"\b\d{4,}\b", "<NUM>", msg)               # Strip long numbers
    return msg.strip()
```

This means two failures with messages like:
- `"Connection refused at /var/run/postgres/5432 at 2024-01-01T10:00:00Z"`
- `"Connection refused at /tmp/pg/5432 at 2024-03-15T08:30:00Z"`

...both normalise to `"Connection refused at <PATH><NUM>"` and form the same cluster.

Failures are then grouped into `FailurePattern` objects. Clusters with fewer than `min_cluster_size` members are filtered out.

### Key design choices

- **Pre-clustering saves GPT calls**: 50 failures with 5 distinct root causes → 5 GPT calls, not 50.
- **Regex normalisation is fast and deterministic**: no ML, no embeddings, no latency.
- **`representative_errors`** selects up to 5 unique normalised error strings from across the cluster — providing GPT with varied examples while keeping tokens low.

### Configuration

| Env var | Default | Description |
|---|---|---|
| `MIN_CLUSTER_SIZE` | `2` | Minimum failures to form a pattern (filters one-off noise) |

---

## Component 3 — RootCauseClusterer

**File:** [`scenario-1-build-intelligence/agent/root_cause_clusterer.py`](../scenario-1-build-intelligence/agent/root_cause_clusterer.py)

### Responsibility

Sends each `FailurePattern` to GPT-4o and receives a structured root cause analysis.

### How it works

For each pattern, two messages are assembled and sent to the Azure OpenAI chat completions endpoint:

**System prompt** — establishes the role and enforces JSON-only output:

```
You are a senior DevOps engineer and build reliability expert.
...
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
```

**User prompt** — provides the pattern data:

```markdown
## Failure Pattern: `run-tests::ImportError cannot import`

**Occurrence count:** 8
**Affected pipelines:** ci-pipeline, nightly-regression
**Affected branches:** main, feature/auth-refactor

**Representative error messages:**
  - ImportError cannot import name JSONDecodeError from requests.exceptions
  - ...
```

**Settings:**
- Temperature: `0.2` — deterministic, consistent output
- Max tokens: controlled by `GPT_MAX_TOKENS` env var (default `2000`)

**Response parsing:**
- Response is `json.loads()`-parsed directly
- If JSON parsing fails, a graceful fallback `RootCauseFinding` is created using the raw text as the root cause, severity defaults to `MEDIUM`
- If the GPT call raises an exception, that pattern is skipped and logged as an error — it does not abort the whole cycle

### Configuration

| Env var | Default | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | *(required)* | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | *(required)* | API key |
| `AZURE_OPENAI_DEPLOYMENT` | *(required)* | Model deployment name (e.g. `gpt-4o`) |
| `AZURE_OPENAI_API_VERSION` | `2024-02-01` | API version |
| `GPT_TEMPERATURE` | `0.2` | Sampling temperature |
| `GPT_MAX_TOKENS` | `2000` | Max tokens per GPT response |

---

## Component 4 — WikiPublisher

**File:** [`scenario-1-build-intelligence/agent/wiki_publisher.py`](../scenario-1-build-intelligence/agent/wiki_publisher.py)

### Responsibility

Renders the findings as a structured Markdown document and upserts it to an Azure DevOps Wiki page.

### How it works

**Rendering** (`render_wiki_page()`):

Builds a Markdown document with:
- Header with generation timestamp and pattern count
- Numbered table of contents with severity emoji (🔴 CRITICAL, 🟠 HIGH, 🟡 MEDIUM, 🟢 LOW)
- Per-finding sections containing:
  - Severity, occurrence count, affected pipelines and branches (as a table)
  - Root cause paragraph
  - Numbered remediation steps

**Publishing** (`publish()`):

1. Checks if the page already exists by calling `get_wiki_page_version()` to retrieve its ETag
2. If the page exists, passes the ETag in an `If-Match` header (optimistic concurrency — prevents overwriting concurrent edits)
3. Calls `ADOClient.upsert_wiki_page()` which issues:
   ```
   PUT /{org}/{project}/_apis/wiki/wikis/{wiki_id}/pages?api-version=7.1&path={path}
   Body: {"content": "<markdown>"}
   ```
4. If ADO returns `404` (ancestor pages missing), `_ensure_wiki_ancestors()` walks up the path and creates each missing parent page before retrying

**Example generated page structure:**

```markdown
# 🤖 AI Build Intelligence — Failure Report
_Generated by the AI Build Intelligence agent on 2026-04-27T08:43:39Z_
_Total patterns identified: **5**_

## Table of Contents
1. [🔴 Docker Base Image Tag Not Found](#1-docker-base-image-tag-not-found)
2. [🟠 PostgreSQL Connection Refused in Integration Tests](#2-postgresql-...)
...

## 1. 🔴 Docker Base Image Tag Not Found
| Field | Value |
|---|---|
| Severity | CRITICAL |
| Occurrences | 5 |
...
### Root Cause
The Dockerfile references `python:3.11.2-slim-bullseye` which has been removed...

### Remediation Steps
1. Update the FROM tag to `python:3.11-slim`
2. Pin to a digest rather than a mutable tag
...
```

### Configuration

| Env var | Default | Description |
|---|---|---|
| `ADO_WIKI_ID` | *(required)* | Wiki GUID (e.g. `99decd2c-7ad2-4d71-9eb2-6569cede176b`) |
| `ADO_WIKI_PATH` | `/Build-Intelligence/Failure-Report` | Target wiki page path |

---

## Component 5 — Orchestrator

**File:** [`scenario-1-build-intelligence/agent/orchestrator.py`](../scenario-1-build-intelligence/agent/orchestrator.py)

### Responsibility

Entry point that wires together all 4 components in sequence and exposes the `--dry-run` flag.

### Execution flow

```python
def run(pipeline_ids=None, top=None, dry_run=False):
    failures = BuildFailureFetcher().fetch(pipeline_ids, top)
    if not failures:
        return {"failures_count": 0, ...}

    patterns = FailurePatternMiner(min_cluster_size).mine(failures)
    if not patterns:
        return {"failures_count": N, "patterns_count": 0, ...}

    findings = RootCauseClusterer().analyse(patterns)
    findings.sort(key=lambda f: severity_order[f.severity])  # CRITICAL first

    if dry_run:
        return {"markdown": render_wiki_page(findings), ...}
    else:
        wiki_path = WikiPublisher().publish(findings)
        return {"wiki_path": wiki_path, ...}
```

### Dry-run mode

When `--dry-run` is passed (or `dry_run=True`), the Wiki publish step is skipped and the rendered Markdown is returned in the result dict instead. This is useful for:
- Local development and testing without affecting the live Wiki
- Pipeline preview runs
- Debugging GPT output before publishing

---

## Component 6 — Shared Libraries

### `ADOClient` — [`shared/ado_client.py`](../shared/ado_client.py)

Central REST client for all Azure DevOps API calls. Authenticated via HTTP Basic auth with a PAT token.

Key methods used by Scenario 1:

| Method | API call | Used by |
|---|---|---|
| `get_builds()` | `GET /build/builds` | BuildFailureFetcher |
| `get_build_timeline()` | `GET /build/builds/{id}/timeline` | BuildFailureFetcher |
| `extract_build_failures()` | Combines above two | BuildFailureFetcher |
| `get_wiki_page()` | `GET /wiki/wikis/{id}/pages` | WikiPublisher |
| `upsert_wiki_page()` | `PUT /wiki/wikis/{id}/pages` | WikiPublisher |
| `_ensure_wiki_ancestors()` | Creates missing parent pages | WikiPublisher (internal) |

**Retry policy:** 3 retries, 1-second backoff, triggers on HTTP `429`, `500`, `502`, `503`, `504`.

### `AzureOpenAIClient` — [`shared/azure_openai_client.py`](../shared/azure_openai_client.py)

Thin wrapper around the `openai` Python SDK configured for Azure.

Key method used by Scenario 1:

| Method | Description |
|---|---|
| `chat(messages, temperature, max_tokens)` | Sends a chat completion request, returns the assistant message string |

### `utils` — [`shared/utils.py`](../shared/utils.py)

| Function | Used by | Purpose |
|---|---|---|
| `configure_logging()` | Orchestrator | Sets up structured stdout logging |
| `parse_pipeline_ids(raw)` | BuildFailureFetcher | Parses `"1,2,3"` → `[1, 2, 3]` |
| `truncate(text, max_chars)` | FailurePatternMiner, RootCauseClusterer | Limits string length before sending to GPT |
| `utcnow_iso()` | WikiPublisher | Generates the report generation timestamp |

---

## MCP Tool Layer

**Files:** [`scenario-1-build-intelligence/mcp/mcp_tools.py`](../scenario-1-build-intelligence/mcp/mcp_tools.py), [`mcp_server_config.json`](../scenario-1-build-intelligence/mcp/mcp_server_config.json)

Each agent step is also exposed as an individually callable **MCP tool**, enabling the pipeline to be driven by an MCP-aware AI runner or orchestration framework:

| Tool | Wraps | Description |
|---|---|---|
| `tool_get_failed_builds` | `BuildFailureFetcher.fetch()` | Returns raw failure records as JSON |
| `tool_mine_failure_patterns` | `FailurePatternMiner.mine()` | Groups failures into patterns |
| `tool_analyse_root_causes` | `RootCauseClusterer.analyse()` | Calls GPT-4o, returns findings |
| `tool_publish_wiki_page` | `WikiPublisher.publish()` | Renders and upserts the Wiki page |
| `tool_render_wiki_markdown` | `render_wiki_page()` | Returns rendered Markdown without publishing |

---

## Azure Pipeline

**File:** [`scenario-1-build-intelligence/pipelines/azure-pipelines.yml`](../scenario-1-build-intelligence/pipelines/azure-pipelines.yml)

| Property | Value |
|---|---|
| Trigger | Manual or scheduled (daily 06:00 UTC) |
| Agent pool | `ubuntu-latest` |
| Python version | `3.11` |
| Variable group | `ai-devsecops-secrets` |
| Steps | Install deps → Run unit tests → Execute orchestrator → Publish test artifact |

**Runtime parameters** (overridable at queue time):

| Parameter | Default | Description |
|---|---|---|
| `pipelineIds` | *(empty — all)* | Comma-separated pipeline IDs to analyse |
| `maxBuildRuns` | `100` | Max failed builds to fetch |
| `minClusterSize` | `2` | Min failures per cluster |
| `dryRun` | `false` | Skip Wiki publish, print Markdown only |

---

## Demo App Pipeline

**File:** [`scenario-1-build-intelligence/pipelines/demo-app-pipeline.yml`](../scenario-1-build-intelligence/pipelines/demo-app-pipeline.yml)

A purpose-built pipeline for showcasing Scenario 1. It simulates five realistic failure types on an `orders-service` microservice:

| Stage | Failure simulated | Representative error |
|---|---|---|
| Build | Dependency conflict | `urllib3==2.0.0` incompatible with `requests==2.28.0` |
| Integration | DB connection refused | `psycopg2.OperationalError: ...port 5432 failed: Connection refused` |
| CodeQuality | Lint violations | `flake8 E302/E501/F401`, Black formatting failures |
| Docker | Missing base image | `manifest for python:3.11.2-slim-bullseye not found` |
| Deploy | Missing secrets | `DATABASE_URL`, `JWT_SECRET_KEY`, `STRIPE_API_KEY`, `REDIS_URL` not set |

The `failureScenario` parameter lets you target individual failure types or trigger all five at once (`all`). Running this pipeline multiple times seeds enough failure history for the AI Build Intelligence agent to produce a meaningful clustered report.

---

## Error Handling Summary

| Scenario | Behaviour |
|---|---|
| ADO API returns `429` | Retried up to 3 times with exponential backoff |
| Build timeline returns `404` | That failure is included without task detail; logged as `WARNING` |
| GPT returns invalid JSON | Fallback `RootCauseFinding` created; logged as `WARNING` |
| GPT call raises exception | That pattern is skipped; logged as `ERROR`; others continue |
| Wiki page ancestor missing | Parent pages auto-created before the target page is written |
| Wiki ETag conflict (`412`) | ETag re-fetched and upsert retried |
| `ADO_WIKI_ID` not set | `EnvironmentError` raised immediately (fast-fail) |
