# AI DevSecOps Showcase

An end-to-end showcase of AI-powered DevSecOps automation using Python 3.11, Azure OpenAI, and Azure DevOps. Two production-ready scenarios demonstrate how AI agents can autonomously improve build reliability and enforce compliance standards.

---

## 🚀 Scenarios

### Scenario 1 — AI Build Intelligence
**Pipeline failure pattern mining → GPT root cause clustering → Auto-published remediation wiki**

Azure DevOps pipeline failure data is ingested, semantically clustered by GPT, and actionable remediation steps are auto-published to an Azure DevOps Wiki page — keeping the team informed with zero manual effort.

[→ Scenario 1 README](scenario-1-build-intelligence/README.md)

### Scenario 2 — AI PR Compliance
**Confluence standards + tech docs → AI PR reviewer → Automated compliance gate**

Engineering standards and technical documentation are pulled from Confluence. An AI agent reviews pipeline YAML and code changes in every PR against those standards, posts inline feedback, and blocks the PR on FAIL.

[→ Scenario 2 README](scenario-2-compliance-standards/README.md)

---

## 📁 Repository Structure

```
ai-devsecops-showcase/
├── scenario-1-build-intelligence/
│   ├── agent/              # Python agent scripts
│   ├── mcp/                # MCP server config & tools
│   ├── pipelines/          # Azure Pipelines YAML
│   ├── tests/              # Unit & integration tests
│   ├── requirements.txt
│   └── README.md
├── scenario-2-compliance-standards/
│   ├── agent/              # Python agent scripts
│   ├── mcp/                # MCP server config & tools
│   ├── pipelines/          # Azure Pipelines YAML
│   ├── tests/              # Unit & integration tests
│   ├── requirements.txt
│   └── README.md
├── shared/                 # Shared clients & utilities
├── docs/                   # Architecture & setup docs
├── .env.example
├── docker-compose.yml
└── README.md               ← you are here
```

---

## ⚡ Quick Start

### Prerequisites
- Python 3.11+
- Azure DevOps organization with a PAT token
- Azure OpenAI deployment (GPT-4o recommended)
- Confluence Cloud account (for Scenario 2)
- Docker + Docker Compose (optional, for containerized run)

### 1. Clone & configure

```bash
git clone https://github.com/smodede/ai-devsecops-showcase.git
cd ai-devsecops-showcase
cp .env.example .env
# Edit .env with your credentials
```

### 2. Install dependencies

**Scenario 1:**
```bash
cd scenario-1-build-intelligence
pip install -r requirements.txt
```

**Scenario 2:**
```bash
cd scenario-2-compliance-standards
pip install -r requirements.txt
```

### 3. Run via Docker Compose

```bash
docker-compose up scenario-1
# or
docker-compose up scenario-2
```

---

## 🔑 Environment Variables

See [.env.example](.env.example) for all required configuration.

| Variable | Description |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | GPT model deployment name (e.g. `gpt-4o`) |
| `AZURE_OPENAI_API_VERSION` | API version (e.g. `2024-02-01`) |
| `ADO_ORGANIZATION_URL` | Azure DevOps org URL |
| `ADO_PROJECT` | Azure DevOps project name |
| `ADO_PAT` | Azure DevOps Personal Access Token |
| `CONFLUENCE_URL` | Confluence base URL (Scenario 2) |
| `CONFLUENCE_USERNAME` | Confluence username/email (Scenario 2) |
| `CONFLUENCE_API_TOKEN` | Confluence API token (Scenario 2) |

---

## 🏗️ Architecture

See [docs/architecture.md](docs/architecture.md) for the full architecture overview.

---

## 📖 Documentation

- [Architecture Overview](docs/architecture.md)
- [Setup Guide](docs/setup-guide.md)
- [Scenario 1 Design](docs/scenario-1-design.md)
- [Scenario 2 Design](docs/scenario-2-design.md)

---

## 🧪 Running Tests

```bash
# From repository root
pip install pytest pytest-asyncio pytest-mock

# Scenario 1 tests
pytest scenario-1-build-intelligence/tests/ -v

# Scenario 2 tests
pytest scenario-2-compliance-standards/tests/ -v
```

---

## License

MIT