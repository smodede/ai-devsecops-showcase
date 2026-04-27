# Scenario 2 - AI Compliance Standards

## Overview

On every Pull Request targeting `main`, `develop`, or `release/*`, this agent:

1. Reads your DevSecOps standards from **Confluence** via the Atlassian Remote MCP server (SSE)
2. Fetches the PR pipeline YAML and changed files from **Azure DevOps** via the ADO MCP server
3. Assesses compliance using **Azure OpenAI GPT-4o**
4. Posts a structured compliance report as a **PR comment**
5. **Blocks merge** if critical standards are violated (exit code 1 fails the pipeline)

## Architecture

```
Confluence Space (DevSecOps Standards)
        |
        v  (MCP: Atlassian Remote SSE - https://mcp.atlassian.com/v1/sse)
Standards Ingestion
- Searches space for devsecops-standard labelled pages
- Fetches known standards pages by title
- Strips HTML, normalises content
        |
        v
AI Compliance Assessor (Azure OpenAI GPT-4o)
- Compares pipeline YAML + changed files against standards
- Produces PASS / WARN / FAIL per standard
- Generates human-readable remediation comments
        |
        v  (MCP: @tiberriver256/mcp-server-azure-devops via stdio)
PR Feedback Publisher
- Posts structured compliance report as PR thread comment
- Votes "Needs Work" (-5) on PR if blocking
- Pipeline exits code 1 to fail the ADO build gate
```

## GitHub + Azure DevOps Integration

The pipeline YAML lives in this **GitHub repo** and is executed by **Azure DevOps** on every PR.

To set this up:
1. In Azure DevOps: **Project Settings > Service connections > New > GitHub**
2. Name the connection `github-service-connection`
3. Go to **Pipelines > New Pipeline > GitHub > smodede/ai-devsecops-showcase**
4. Select **Existing Azure Pipelines YAML file**
5. Path: `scenario-2-compliance-standards/pipelines/azure-pipelines.yml`
6. Set as a **required** Branch Policy on `main` for mandatory compliance checking

## Sample PR Comment

```
## ❌ AI DevSecOps Compliance Report - FAILED - MERGE BLOCKED

> This PR introduces hardcoded credentials in the pipeline definition and is
> missing mandatory SAST scanning. Two critical compliance failures must be
> remediated before merge.

### Summary
| ❌ Failures | ⚠️ Warnings | ✅ Passed |
|------------|------------|----------|
| **2**      | **1**      | **6**    |

### ❌ Compliance Failures (Must Fix Before Merge)

🔴 [DS-001] Secret Management - Hardcoded credentials detected
Finding: Line 34 of azure-pipelines.yml contains a hardcoded API key value.
Remediation: Move the value to an Azure DevOps Variable Group linked to Key Vault.
```

## Setup

### 1. Label Confluence Pages
Add the label `devsecops-standard` to your Confluence standards pages,
or update `STANDARDS_PAGES` in `agent/confluence_reader.py` with your exact page titles.

### 2. Variable Group: `ai-devsecops-secrets`

| Variable | Description | Secret |
|----------|-------------|--------|
| `AZURE_DEVOPS_ORG_URL` | `https://dev.azure.com/your-org` | No |
| `AZURE_DEVOPS_PAT` | PAT: Code Read + PR Write permissions | Yes |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | No |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | Yes |
| `AZURE_OPENAI_DEPLOYMENT` | e.g. `gpt-4o` | No |
| `AZURE_OPENAI_API_VERSION` | e.g. `2024-08-01-preview` | No |
| `CONFLUENCE_BASE_URL` | e.g. `https://your-org.atlassian.net/wiki` | No |
| `CONFLUENCE_USER_EMAIL` | Service account email | No |
| `CONFLUENCE_API_TOKEN` | Confluence API token | Yes |
| `CONFLUENCE_SPACE_KEY` | e.g. `DEVSECOPS` | No |

### 3. Branch Policy (Recommended)
**Repos > Branches > main > Branch Policies > Build Validation**
Add the compliance pipeline as a **required** status check.
