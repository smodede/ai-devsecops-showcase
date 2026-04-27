# Architecture Overview

## AI DevSecOps Showcase — System Architecture

---

## High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AI DevSecOps Showcase                            │
│                                                                         │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐    │
│  │  Scenario 1                  │  │  Scenario 2                  │    │
│  │  AI Build Intelligence       │  │  AI PR Compliance            │    │
│  │                              │  │                              │    │
│  │  Azure DevOps Builds         │  │  Confluence Standards        │    │
│  │        │                     │  │        │                     │    │
│  │        ▼                     │  │        ▼                     │    │
│  │  FailureFetcher              │  │  ConfluenceFetcher           │    │
│  │        │                     │  │        │                     │    │
│  │        ▼                     │  │        ▼                     │    │
│  │  PatternMiner                │  │  ComplianceChecker           │    │
│  │        │                     │  │        │                     │    │
│  │        ▼                     │  │        ▼                     │    │
│  │  RootCauseClusterer          │  │  PRReviewer                  │    │
│  │  (GPT-4o)                    │  │  (GPT-4o)                    │    │
│  │        │                     │  │        │                     │    │
│  │        ▼                     │  │        ▼                     │    │
│  │  WikiPublisher               │  │  PR Comment + Status         │    │
│  │  (ADO Wiki)                  │  │  (Block / Approve)           │    │
│  └──────────────────────────────┘  └──────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Shared Libraries                                               │   │
│  │  - AzureOpenAIClient   (chat completions + embeddings)         │   │
│  │  - ADOClient           (builds, PRs, Wiki — REST API v7.1)     │   │
│  │  - utils               (logging, formatting, helpers)          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Scenario 1 — AI Build Intelligence

### Data Flow

1. **BuildFailureFetcher** calls `GET /build/builds?resultFilter=failed` to retrieve the N most recent failed pipeline runs.
2. For each failed build, it fetches the build timeline (`GET /build/builds/{id}/timeline`) to extract failed task names and error messages.
3. **FailurePatternMiner** groups failures into buckets by `(task_name, normalised_error_prefix)`. Volatile tokens (GUIDs, timestamps, paths) are stripped before grouping.
4. **RootCauseClusterer** sends each pattern to GPT-4o with a structured prompt requesting:
   - A human-readable title
   - Severity rating (CRITICAL / HIGH / MEDIUM / LOW)
   - Root cause explanation
   - 3–5 remediation steps
5. **WikiPublisher** renders findings as Markdown and upserts the Azure DevOps Wiki page via `PUT /wiki/wikis/{id}/pages`.

### Scheduling

The ADO pipeline runs on a daily cron schedule (06:00 UTC) or can be triggered manually. It can also be invoked from any CI event.

---

## Scenario 2 — AI PR Compliance

### Data Flow

1. **ConfluenceFetcher** pulls engineering standards from one or more Confluence spaces via `GET /rest/api/content`. HTML is stripped to plain text.
2. On a PR event (open / update), **ADOClient** fetches the changed file list (`GET /git/repositories/{repo}/pullrequests/{id}/iterations/{n}/changes`) and downloads file content for text-based files.
3. **ComplianceChecker** sends the standards context + file content to GPT-4o, receiving a structured JSON compliance report with verdict (PASS/FAIL) and per-file findings.
4. **PRReviewer** posts a Markdown comment thread on the PR and sets a custom PR status (`ai-devsecops/ai-pr-compliance`) to `succeeded` or `failed`.
5. A **branch policy** in Azure DevOps requires the `ai-pr-compliance` status check before merging — blocking non-compliant PRs.

### Trigger Modes

| Mode | Description |
|---|---|
| CLI (`--pr-id N`) | Run directly, useful for local testing and CI jobs |
| Webhook server (`--serve`) | FastAPI server receiving ADO Service Hook events |
| ADO Pipeline | Triggered via API call with `prId` parameter from a service hook |

---

## Technology Stack

| Component | Technology |
|---|---|
| Agent runtime | Python 3.11 |
| LLM backend | Azure OpenAI (GPT-4o) |
| ADO integration | ADO REST API v7.1 (requests + Basic auth PAT) |
| Confluence integration | Confluence Cloud REST API v2 |
| Webhook server | FastAPI + uvicorn |
| CI/CD pipelines | Azure Pipelines YAML |
| Containerisation | Docker + Docker Compose |
| Testing | pytest + pytest-mock |
| MCP tooling | MCP server config JSON + Python tool handlers |

---

## Security Considerations

- All secrets (API keys, PATs, tokens) are stored in Azure DevOps **Variable Groups** and never committed to source control.
- The `.env` file is gitignored; only `.env.example` (with placeholder values) is committed.
- Azure OpenAI responses are validated as JSON before use; invalid responses are handled gracefully.
- Confluence content is HTML-stripped before being sent to GPT, reducing injection risks.
- ADO REST API calls use retry logic with exponential backoff; 401/403 errors are surfaced clearly.
- PR comments are posted under the pipeline service account identity.

---

## MCP Integration

Both scenarios expose their pipeline steps as MCP (Model Context Protocol) tools, enabling:
- **Orchestration** by MCP-aware AI frameworks (e.g. AutoGen, Semantic Kernel).
- **Tool composition** — an outer AI agent can invoke `get_failed_builds` → `mine_failure_patterns` → `analyse_root_causes` → `publish_wiki_report` as discrete steps.
- **Observability** — each tool call is independently logged and auditable.

See `scenario-1-build-intelligence/mcp/mcp_server_config.json` and `scenario-2-compliance-standards/mcp/mcp_server_config.json` for the full tool schemas.
