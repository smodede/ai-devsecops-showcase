# Azure DevOps Setup Guide

This guide walks through connecting Azure DevOps to the `smodede/ai-devsecops-showcase`
GitHub repository and importing both pipelines.

## Prerequisites

- Azure DevOps organisation with at least one project
- GitHub account with access to `smodede/ai-devsecops-showcase`
- Azure OpenAI deployment (GPT-4o recommended)
- Confluence Cloud account (Scenario 2 only)

---

## Step 1: Create GitHub Service Connection

1. In Azure DevOps, go to **Project Settings** (bottom-left gear icon)
2. Under **Pipelines**, select **Service connections**
3. Click **New service connection > GitHub**
4. Choose **GitHub App** (recommended) or **Personal Access Token**
5. Name the connection exactly: `github-service-connection`
6. Grant access to the `smodede/ai-devsecops-showcase` repository
7. Click **Save**

> The name `github-service-connection` must match exactly — it is referenced
> in both `azure-pipelines.yml` files under `resources.repositories.endpoint`.

---

## Step 2: Create Variable Group

1. Go to **Pipelines > Library > + Variable group**
2. Name it exactly: `ai-devsecops-secrets`
3. Add all variables from the table below
4. Mark secret variables with the lock icon
5. Click **Save**

### Variables Required

| Variable | Description | Secret |
|----------|-------------|--------|
| `AZURE_DEVOPS_ORG_URL` | `https://dev.azure.com/your-org` | No |
| `AZURE_DEVOPS_PAT` | PAT with Build Read, Wiki Write, PR Write | Yes |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint | No |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | Yes |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name e.g. `gpt-4o` | No |
| `AZURE_OPENAI_API_VERSION` | e.g. `2024-08-01-preview` | No |
| `CONFLUENCE_BASE_URL` | `https://your-org.atlassian.net/wiki` | No |
| `CONFLUENCE_USER_EMAIL` | Confluence service account email | No |
| `CONFLUENCE_API_TOKEN` | Confluence API token | Yes |
| `CONFLUENCE_SPACE_KEY` | Confluence space key e.g. `DEVSECOPS` | No |

### Link to Azure Key Vault (Recommended for Production)
1. In the Variable Group, enable **Link secrets from an Azure key vault**
2. Select your subscription and Key Vault
3. Add the secret variables from the table above as Key Vault references

---

## Step 3: Import Scenario 1 Pipeline (Build Intelligence)

1. Go to **Pipelines > New pipeline**
2. Select **GitHub** as source
3. Authenticate and select `smodede/ai-devsecops-showcase`
4. Choose **Existing Azure Pipelines YAML file**
5. Branch: `main` | Path: `scenario-1-build-intelligence/pipelines/azure-pipelines.yml`
6. Click **Continue > Save** (do not run yet)
7. Go to pipeline settings and grant access to the `ai-devsecops-secrets` variable group
8. Rename the pipeline to `AI-Build-Intelligence`

---

## Step 4: Import Scenario 2 Pipeline (Compliance Standards)

1. Go to **Pipelines > New pipeline**
2. Select **GitHub** as source
3. Select `smodede/ai-devsecops-showcase`
4. Choose **Existing Azure Pipelines YAML file**
5. Branch: `main` | Path: `scenario-2-compliance-standards/pipelines/azure-pipelines.yml`
6. Click **Continue > Save**
7. Grant access to the `ai-devsecops-secrets` variable group
8. Rename to `AI-Compliance-Standards`

---

## Step 5: Set Branch Policy (Mandatory Compliance - Recommended)

To make the compliance check a required gate on `main`:

1. Go to **Repos > Branches**
2. Click the `...` menu on `main` > **Branch policies**
3. Under **Build validation**, click **+**
4. Select the `AI-Compliance-Standards` pipeline
5. Set **Trigger** to Automatic, **Policy requirement** to Required
6. Click **Save**

---

## Step 6: Test the Setup

### Test Scenario 1
1. Go to `AI-Build-Intelligence` pipeline
2. Click **Run pipeline** manually
3. Check the Azure DevOps Wiki for new pages under `AI DevSecOps Training`

### Test Scenario 2
1. Create a branch from `main` in the GitHub repo
2. Open a Pull Request targeting `main`
3. The `AI-Compliance-Standards` pipeline should trigger automatically
4. Check the PR for a compliance report comment
