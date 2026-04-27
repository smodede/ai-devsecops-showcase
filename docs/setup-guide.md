# Setup Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Use pyenv or system Python |
| pip | latest | `pip install --upgrade pip` |
| Docker + Compose | latest | For containerised run |
| Azure DevOps | - | Organization with at least one project |
| Azure OpenAI | - | GPT-4o deployment recommended |
| Confluence Cloud | - | Required for Scenario 2 only |

---

## 1. Clone the repository

```bash
git clone https://github.com/smodede/ai-devsecops-showcase.git
cd ai-devsecops-showcase
```

---

## 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` in your editor and fill in the required values. See [.env.example](.env.example) for descriptions of each variable.

### Azure OpenAI

1. Go to [portal.azure.com](https://portal.azure.com) → Azure OpenAI → your resource.
2. Copy the **Endpoint** and generate an **API key**.
3. Under **Model Deployments**, note the deployment name (e.g. `gpt-4o`).
4. Set: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`.

### Azure DevOps

1. Go to `https://dev.azure.com/<org>` → User settings → Personal access tokens.
2. Create a token with these scopes:
   - **Build**: Read
   - **Code**: Read, Status
   - **Pull Request Threads**: Read & Write
   - **Wiki**: Read & Write
3. Set: `ADO_ORGANIZATION_URL`, `ADO_PROJECT`, `ADO_PAT`.

### Confluence (Scenario 2 only)

1. Go to [id.atlassian.com](https://id.atlassian.com) → API tokens → Create API token.
2. Set: `CONFLUENCE_URL`, `CONFLUENCE_USERNAME`, `CONFLUENCE_API_TOKEN`.
3. Set `CONFLUENCE_SPACE_KEYS` to the space keys containing your standards (e.g. `ENG,DEVOPS`).

---

## 3. Install dependencies

### Scenario 1

```bash
cd scenario-1-build-intelligence
pip install -r requirements.txt
cd ..
```

### Scenario 2

```bash
cd scenario-2-compliance-standards
pip install -r requirements.txt
cd ..
```

---

## 4. Run tests

```bash
pytest scenario-1-build-intelligence/tests/ -v
pytest scenario-2-compliance-standards/tests/ -v
```

Tests use mocks and do not require real API credentials.

---

## 5. Run locally

### Scenario 1 — Dry run (no Wiki publish)

```bash
python -m scenario-1-build-intelligence.agent.orchestrator --dry-run
```

### Scenario 2 — Review a PR (dry run)

```bash
python -m scenario-2-compliance-standards.agent.orchestrator --pr-id 42 --dry-run
```

---

## 6. Run via Docker Compose

```bash
# Scenario 1 only
docker-compose up scenario-1

# Scenario 2 only (starts webhook server on port 8080)
docker-compose up scenario-2

# Both + MCP server
docker-compose up
```

---

## 7. Configure Azure DevOps pipelines

### Variable Group

1. In ADO: Pipelines → Library → + Variable group.
2. Name it exactly: `ai-devsecops-secrets`.
3. Add all variables from `.env.example` (mark API keys and tokens as **secret**).

### Create pipelines

For each scenario:
1. ADO → Pipelines → New pipeline → Azure Repos Git (or GitHub).
2. Select **Existing Azure Pipelines YAML file**.
3. Path:
   - Scenario 1: `scenario-1-build-intelligence/pipelines/azure-pipelines.yml`
   - Scenario 2: `scenario-2-compliance-standards/pipelines/azure-pipelines.yml`
4. Save and run.

### Scenario 2: Service Hook

1. ADO → Project Settings → Service Hooks → + Subscription.
2. Service: **Web Hooks**.
3. Trigger: **Pull request created** (and repeat for **updated**).
4. URL: `https://<your-webhook-host>/webhook/pr-created`.

### Scenario 2: Branch Policy

1. ADO → Repos → Branches → `main` → Branch Policies.
2. Add **Status Check** policy.
3. Status name: `ai-pr-compliance`, genre: `ai-devsecops`.
4. Mark as **Required**.

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `EnvironmentError: AZURE_OPENAI_ENDPOINT is not set` | Check your `.env` file or variable group |
| `401 Unauthorized` from ADO | Regenerate PAT; check scope includes Code, Build, Wiki, Pull Request |
| `401 Unauthorized` from Confluence | Verify `CONFLUENCE_USERNAME` is your email, `CONFLUENCE_API_TOKEN` is an API token (not your password) |
| GPT returns non-JSON response | Increase `GPT_MAX_TOKENS`; check your deployment quota |
| Wiki page not created | Verify `ADO_WIKI_ID` exists; PAT must have Wiki Write scope |
| PR comment not posted | Verify `ADO_REPOSITORY_ID` is the GUID of the target repository |
