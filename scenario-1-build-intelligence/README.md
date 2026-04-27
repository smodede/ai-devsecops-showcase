# Scenario 1 — AI Build Intelligence

Automatically mines Azure DevOps pipeline failure data, clusters root causes
using GPT-4o, and publishes remediation guidance to an Azure DevOps Wiki.

---

## How It Works

```
Azure DevOps Builds
       │
       ▼
┌─────────────────────┐
│  BuildFailureFetcher│  ← Pulls failed runs + timeline errors via ADO REST API
└─────────┬───────────┘
          │ List[BuildFailure]
          ▼
┌─────────────────────┐
│ FailurePatternMiner │  ← Heuristic clustering by task name + error prefix
└─────────┬───────────┘
          │ List[FailurePattern]
          ▼
┌─────────────────────┐
│ RootCauseClusterer  │  ← GPT-4o: root cause + severity + remediation steps
└─────────┬───────────┘
          │ List[RootCauseFinding]
          ▼
┌─────────────────────┐
│   WikiPublisher     │  ← Renders Markdown, upserts Azure DevOps Wiki page
└─────────────────────┘
```

---

## Files

```
scenario-1-build-intelligence/
├── agent/
│   ├── build_failure_fetcher.py    # Fetch failed pipeline runs
│   ├── failure_pattern_miner.py   # Heuristic pattern grouping
│   ├── root_cause_clusterer.py    # GPT root cause analysis
│   ├── wiki_publisher.py          # Markdown rendering + Wiki upsert
│   └── orchestrator.py            # Main entry point
├── mcp/
│   ├── mcp_server_config.json     # MCP tool definitions
│   └── mcp_tools.py               # MCP tool implementations
├── pipelines/
│   └── azure-pipelines.yml        # ADO pipeline (scheduled nightly)
├── tests/
│   └── test_build_intelligence.py
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Running Locally

```bash
# 1. From the repo root
cp .env.example .env
# Fill in AZURE_OPENAI_*, ADO_*, ADO_WIKI_ID, ADO_WIKI_PATH

# 2. Install dependencies
cd scenario-1-build-intelligence
pip install -r requirements.txt

# 3. Run (dry-run mode — prints Markdown, skips Wiki publish)
cd ..
python -m scenario-1-build-intelligence.agent.orchestrator --dry-run

# 4. Run (live — publishes to Wiki)
python -m scenario-1-build-intelligence.agent.orchestrator
```

---

## Running via Docker

```bash
docker-compose up scenario-1
```

---

## Pipeline Setup in Azure DevOps

1. Create a **Variable Group** named `ai-devsecops-secrets` in Azure DevOps
   Pipelines → Library with the following variables:

   | Variable | Description |
   |---|---|
   | `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint |
   | `AZURE_OPENAI_API_KEY` | Azure OpenAI key (mark as secret) |
   | `AZURE_OPENAI_DEPLOYMENT` | Deployment name (e.g. `gpt-4o`) |
   | `AZURE_OPENAI_API_VERSION` | API version (e.g. `2024-02-01`) |
   | `ADO_ORGANIZATION_URL` | ADO org URL |
   | `ADO_PROJECT` | ADO project name |
   | `ADO_PAT` | Personal Access Token (mark as secret) |
   | `ADO_WIKI_ID` | Wiki ID to publish to |
   | `ADO_WIKI_PATH` | Wiki page path (e.g. `/AI-Reports/Build-Failures`) |

2. Create a new pipeline in Azure DevOps pointing to
   `scenario-1-build-intelligence/pipelines/azure-pipelines.yml`.

3. The pipeline runs automatically at **06:00 UTC daily** or on manual trigger.

---

## Tests

```bash
pytest scenario-1-build-intelligence/tests/ -v
```

---

## Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ADO_PIPELINE_IDS` | _(all)_ | Comma-separated pipeline IDs to monitor |
| `MAX_BUILD_RUNS` | `100` | Max failed builds to fetch per cycle |
| `MIN_CLUSTER_SIZE` | `2` | Min occurrences to form a pattern |
| `GPT_TEMPERATURE` | `0.2` | GPT temperature for analysis |
| `GPT_MAX_TOKENS` | `2000` | Max tokens per GPT response |
