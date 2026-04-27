# Variable Groups Reference

This document is the complete reference for the `ai-devsecops-secrets` Azure DevOps
Variable Group used by both scenarios.

## Variable Group Name

`ai-devsecops-secrets`

This exact name is referenced in both pipeline YAML files:
```yaml
variables:
  - group: ai-devsecops-secrets
```

---

## Complete Variable Reference

### Azure DevOps Variables

| Variable | Required By | Description | Secret | Example |
|----------|-------------|-------------|--------|---------|
| `AZURE_DEVOPS_ORG_URL` | Both | Your ADO organisation URL | No | `https://dev.azure.com/myorg` |
| `AZURE_DEVOPS_PAT` | Both | Personal Access Token | Yes | — |

#### PAT Permissions Required

| Scope | Scenario 1 | Scenario 2 |
|-------|-----------|-----------|
| Build (Read) | Required | Required |
| Wiki (Read & Write) | Required | Not needed |
| Code (Read) | Not needed | Required |
| Pull Request Threads (Read & Write) | Not needed | Required |

---

### Azure OpenAI Variables

| Variable | Required By | Description | Secret | Example |
|----------|-------------|-------------|--------|---------|
| `AZURE_OPENAI_ENDPOINT` | Both | Azure OpenAI resource endpoint | No | `https://myinstance.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | Both | Azure OpenAI API key | Yes | — |
| `AZURE_OPENAI_DEPLOYMENT` | Both | Model deployment name | No | `gpt-4o` |
| `AZURE_OPENAI_API_VERSION` | Both | API version | No | `2024-08-01-preview` |

---

### Confluence Variables (Scenario 2 Only)

| Variable | Required By | Description | Secret | Example |
|----------|-------------|-------------|--------|---------|
| `CONFLUENCE_BASE_URL` | Scenario 2 | Confluence base URL | No | `https://myorg.atlassian.net/wiki` |
| `CONFLUENCE_USER_EMAIL` | Scenario 2 | Service account email | No | `svc-devsecops@example.com` |
| `CONFLUENCE_API_TOKEN` | Scenario 2 | Atlassian API token | Yes | — |
| `CONFLUENCE_SPACE_KEY` | Scenario 2 | Confluence space key | No | `DEVSECOPS` |

---

## Azure Key Vault Mapping (Production)

For production, store secrets in Azure Key Vault and link them to the Variable Group.

| Key Vault Secret Name | Maps To Variable |
|----------------------|-----------------|
| `azure-devops-pat` | `AZURE_DEVOPS_PAT` |
| `azure-openai-api-key` | `AZURE_OPENAI_API_KEY` |
| `confluence-api-token` | `CONFLUENCE_API_TOKEN` |
