# Scenario 2 — AI PR Compliance

Automatically reviews pull requests against Confluence-sourced engineering
standards. An AI agent checks pipeline YAML and source code for compliance,
posts structured feedback on the PR, and blocks merging on FAIL via Azure
DevOps branch policies.

---

## How It Works

```
Confluence Spaces / Pages
         │
         ▼
┌─────────────────────┐
│  ConfluenceFetcher  │  ← Pulls standards from Confluence REST API
└─────────┬───────────┘
          │ List[StandardsDocument]
          ▼
┌─────────────────────┐      Azure DevOps PR
│  ADOClient          │ ←── Get changed files (YAML, Python, …)
└─────────┬───────────┘
          │ Dict[path, content]
          ▼
┌─────────────────────┐
│  ComplianceChecker  │  ← GPT-4o: evaluate files against standards
└─────────┬───────────┘
          │ ComplianceReport (PASS / FAIL + findings)
          ▼
┌─────────────────────┐
│    PRReviewer       │  ← Post comment thread + set PR status
└─────────────────────┘
         │
         ▼
   PR blocked (FAIL)
   or approved (PASS)
```

---

## Files

```
scenario-2-compliance-standards/
├── agent/
│   ├── confluence_fetcher.py    # Pull standards from Confluence
│   ├── compliance_checker.py   # GPT compliance evaluation
│   ├── pr_reviewer.py          # Post feedback + update PR status
│   └── orchestrator.py         # Main entry point (CLI + webhook server)
├── mcp/
│   ├── mcp_server_config.json  # MCP tool definitions
│   └── mcp_tools.py            # MCP tool implementations
├── pipelines/
│   └── azure-pipelines.yml     # ADO pipeline (triggered by service hook)
├── tests/
│   └── test_pr_compliance.py
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Running Locally

### CLI mode (review a single PR)

```bash
# From repo root
cp .env.example .env
# Fill in all CONFLUENCE_* and ADO_* variables

cd scenario-2-compliance-standards
pip install -r requirements.txt
cd ..

# Dry run — prints Markdown, skips posting to PR
python -m scenario-2-compliance-standards.agent.orchestrator --pr-id 42 --dry-run

# Live run — posts comment and sets PR status
python -m scenario-2-compliance-standards.agent.orchestrator --pr-id 42
```

### Webhook server mode (handles ADO service hook events)

```bash
python -m scenario-2-compliance-standards.agent.orchestrator --serve --port 8080
```

The server exposes:
- `POST /webhook/pr-created` — triggered when a PR is opened
- `POST /webhook/pr-updated` — triggered when a PR is updated
- `GET /health` — health check

---

## Running via Docker

```bash
docker-compose up scenario-2
```

The container starts the webhook server on port 8080.

---

## Pipeline Setup in Azure DevOps

### 1. Variable Group

Create a Variable Group named `ai-devsecops-secrets` in ADO Pipelines → Library:

| Variable | Description |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI key (mark as secret) |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name (e.g. `gpt-4o`) |
| `AZURE_OPENAI_API_VERSION` | API version (e.g. `2024-02-01`) |
| `ADO_ORGANIZATION_URL` | ADO org URL |
| `ADO_PROJECT` | ADO project name |
| `ADO_PAT` | PAT with Code Read + PR Write permissions (mark as secret) |
| `ADO_REPOSITORY_ID` | Repository GUID |
| `CONFLUENCE_URL` | Confluence base URL |
| `CONFLUENCE_USERNAME` | Confluence username/email |
| `CONFLUENCE_API_TOKEN` | Confluence API token (mark as secret) |
| `CONFLUENCE_SPACE_KEYS` | Space keys (e.g. `ENG,DEVOPS`) |

### 2. Pipeline

Create a new pipeline pointing to
`scenario-2-compliance-standards/pipelines/azure-pipelines.yml`.

### 3. Service Hook (webhook trigger)

In Azure DevOps → Project Settings → Service Hooks:
1. Create a **Web Hooks** subscription for **Pull request created**.
2. Set the URL to your webhook server: `https://<your-host>/webhook/pr-created`.
3. Repeat for **Pull request updated** → `/webhook/pr-updated`.

### 4. Branch Policy (block on FAIL)

In Repos → Branches → Branch Policies for `main`:
1. Enable **Status Check** policy.
2. Add status: `ai-devsecops/ai-pr-compliance`.
3. Set as **Required** — this blocks merging when the AI compliance check fails.

---

## Tests

```bash
pytest scenario-2-compliance-standards/tests/ -v
```

---

## Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CONFLUENCE_SPACE_KEYS` | _(required)_ | Comma-separated Confluence space keys |
| `CONFLUENCE_STANDARDS_PAGE_IDS` | _(optional)_ | Additional page IDs to always include |
| `ADO_REPOSITORY_ID` | _(required)_ | Repository GUID for posting PR comments |
| `GPT_TEMPERATURE` | `0.1` | GPT temperature (lower = more deterministic) |
| `GPT_MAX_TOKENS` | `3000` | Max tokens per GPT response |
