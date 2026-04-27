# AI DevSecOps Showcase

An AI-powered DevSecOps showcase demonstrating intelligent pipeline operations using
**Azure DevOps pipelines**, **Azure OpenAI (GPT-4o)**, and **MCP (Model Context Protocol)** servers.

## Repository

| Property | Value |
|----------|-------|
| GitHub repo | `smodede/ai-devsecops-showcase` |
| Pipeline execution | Azure DevOps (via GitHub service connection) |
| AI backend | Azure OpenAI GPT-4o |
| MCP servers | Azure DevOps MCP + Atlassian Remote MCP |

---

## Scenarios

### Scenario 1 - AI Build Intelligence & Developer Training

Automatically detects recurring Azure DevOps pipeline failures, analyses patterns using
Azure OpenAI, and publishes targeted training content to the Azure DevOps Wiki.

**Flow:**
```
Azure DevOps Pipelines
        |
        v  (MCP: @tiberriver256/mcp-server-azure-devops)
Build Failure Collector  -->  AI Pattern Analyser (GPT-4o)  -->  Wiki Publisher
```

**Trigger:** Scheduled weekly (Monday 06:00 UTC) or manual

**Output:** Structured training wiki pages per failure category with root cause, resolution steps, and prevention guidance

---

### Scenario 2 - AI Compliance Standards (Confluence -> PR Feedback)

Reads DevSecOps standards from Confluence at runtime, assesses pull request pipeline
definitions and code changes against those standards, and posts structured compliance
feedback directly on the PR - blocking merge if critical standards are violated.

**Flow:**
```
Confluence Space                    GitHub Pull Request
        |                                   |
        v  (MCP: Atlassian Remote SSE)      v  (MCP: ADO MCP)
Standards Ingestion  -->  AI Compliance Assessor (GPT-4o)  -->  PR Comment + Vote
```

**Trigger:** Every PR targeting `main`, `develop`, or `release/*`

**Output:** PASS/WARN/FAIL compliance report as a PR comment; blocks merge on FAIL

---

## MCP Servers

| Server | Package / Endpoint | Transport | Purpose |
|--------|-------------------|-----------|---------|
| Azure DevOps MCP | `@tiberriver256/mcp-server-azure-devops` | stdio (Node.js subprocess) | Read builds, write Wiki, post PR comments |
| Atlassian MCP | `https://mcp.atlassian.com/v1/sse` | SSE (remote HTTP) | Read Confluence standards pages |

---

## Prerequisites

- Python 3.11+
- Node.js 18+ (for Azure DevOps MCP server)
- Azure DevOps organisation
- Azure OpenAI deployment (GPT-4o recommended)
- Confluence Cloud account with API token (Scenario 2)
- GitHub account with access to this repository

---

## Quick Start

### 1. Clone this repository

```bash
git clone https://github.com/smodede/ai-devsecops-showcase.git
cd ai-devsecops-showcase
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

### 3. Install dependencies

```bash
# Scenario 1
pip install -r scenario-1-build-intelligence/requirements.txt

# Scenario 2
pip install -r scenario-2-compliance-standards/requirements.txt
```

### 4. Set up Azure DevOps

Follow the step-by-step guide in [docs/azure-devops-setup.md](docs/azure-devops-setup.md):

1. Create GitHub service connection (`github-service-connection`)
2. Create Variable Group (`ai-devsecops-secrets`) - see [docs/variable-groups.md](docs/variable-groups.md)
3. Import Scenario 1 pipeline
4. Import Scenario 2 pipeline
5. Set branch policy for mandatory compliance checking

### 5. Run locally (optional)

```bash
# Scenario 1 - Build Intelligence
cd scenario-1-build-intelligence
python -m agent.main

# Scenario 2 - Compliance check (requires PR_ID and REPOSITORY_ID)
cd scenario-2-compliance-standards
PR_ID=123 REPOSITORY_ID=my-repo python -m agent.main
```

Or use Docker Compose:

```bash
# Scenario 1
docker compose --profile scenario-1 up

# Scenario 2
PR_ID=123 REPOSITORY_ID=my-repo docker compose --profile scenario-2 up
```

---

## Project Structure

```
ai-devsecops-showcase/
├── scenario-1-build-intelligence/
│   ├── agent/                      # Build collector, pattern analyser, wiki publisher
│   ├── mcp-config/                 # Azure DevOps MCP server config
│   ├── pipelines/                  # azure-pipelines.yml (scheduled)
│   ├── requirements.txt
│   └── README.md
├── scenario-2-compliance-standards/
│   ├── agent/                      # Confluence reader, compliance assessor, PR commenter
│   ├── mcp-config/                 # Azure DevOps + Atlassian MCP server configs
│   ├── pipelines/                  # azure-pipelines.yml (PR trigger)
│   ├── standards-schema/           # Pydantic data models
│   ├── requirements.txt
│   └── README.md
├── shared/
│   ├── mcp_host.py                 # Reusable MCP session managers (stdio + SSE)
│   └── prompts/                    # Azure OpenAI system prompts
├── docs/
│   ├── azure-devops-setup.md       # Step-by-step ADO setup guide
│   └── variable-groups.md          # Complete variable reference
├── docker-compose.yml              # Local dev orchestration
├── .env.example                    # Environment variable template
└── README.md
```

---

## Security Notes

- All secrets are stored in **Azure DevOps Variable Groups** linked to **Azure Key Vault**
- The `.env` file is for **local development only** - never commit it (it is in `.gitignore`)
- Both pipelines include a **detect-secrets scan** as a DevSecOps gate before agent execution
- Azure DevOps PAT tokens should follow **least privilege** - see [docs/variable-groups.md](docs/variable-groups.md) for required scopes
