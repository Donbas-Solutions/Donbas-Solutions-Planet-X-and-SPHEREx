#!/usr/bin/env bash
# One-time Azure setup for .github/workflows/deploy.yml. Safe to rerun.
# Needs `az login` as someone who may create app registrations and assign roles (subscription Owner).
#
#   infra/bootstrap.sh <github-owner>/<repo> [resource-group] [location]
#
# Creates the resource group, an app registration that GitHub Actions signs in as through OIDC (no client secret),
# and its rights on that resource group only: Contributor, plus the right to grant exactly one role (AcrPull),
# which main.bicep needs for the apps' image-pull identity.
set -euo pipefail
# Git Bash on Windows would otherwise turn /subscriptions/... into a file path.
export MSYS_NO_PATHCONV=1

repo=${1:?usage: infra/bootstrap.sh <github-owner>/<repo> [resource-group] [location]}
group=${2:-rg-spherex-blink}
# Azure for Students allows only spaincentral, switzerlandnorth, francecentral, germanywestcentral, polandcentral.
location=${3:-polandcentral}
app_name=spherex-blink-github-deploy
acr_pull=7f951dda-4ed3-4680-a7ca-43fe172d538d

subscription=$(az account show --query id -o tsv)
tenant=$(az account show --query tenantId -o tsv)
scope="/subscriptions/$subscription/resourceGroups/$group"
echo "Subscription $subscription, resource group $group ($location), GitHub repo $repo"

for namespace in Microsoft.App Microsoft.ContainerRegistry Microsoft.OperationalInsights \
  Microsoft.ManagedIdentity Microsoft.Consumption; do
  az provider register --namespace "$namespace" --wait --output none
done

az group create --name "$group" --location "$location" --tags app=spherex-blink --output none

app_id=$(az ad app list --display-name "$app_name" --query '[0].appId' -o tsv)
if [ -z "$app_id" ]; then
  app_id=$(az ad app create --display-name "$app_name" --query appId -o tsv)
fi
sp_id=$(az ad sp show --id "$app_id" --query id -o tsv 2>/dev/null || az ad sp create --id "$app_id" --query id -o tsv)

credential=github-production
if [ -z "$(az ad app federated-credential list --id "$app_id" --query "[?name=='$credential'].name" -o tsv)" ]; then
  az ad app federated-credential create --id "$app_id" --output none --parameters "{
    \"name\": \"$credential\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:$repo:environment:production\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }"
fi

assign() {
  local role=$1
  shift
  if [ -z "$(az role assignment list --assignee "$sp_id" --role "$role" --scope "$scope" --query '[0].id' -o tsv)" ]; then
    az role assignment create --assignee-object-id "$sp_id" --assignee-principal-type ServicePrincipal \
      --role "$role" --scope "$scope" --output none "$@"
  fi
}

assign Contributor
assign "Role Based Access Control Administrator" --condition-version 2.0 --condition "\
((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR \
(@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$acr_pull})) AND \
((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR \
(@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$acr_pull}))"

cat <<EOF

Done. In GitHub → Settings → Secrets and variables → Actions → Variables (repository level), set:
  AZURE_CLIENT_ID        $app_id
  AZURE_TENANT_ID        $tenant
  AZURE_SUBSCRIPTION_ID  $subscription
  AZURE_RESOURCE_GROUP   $group
  AZURE_LOCATION         $location
Optional: BUDGET_EMAIL (monthly cost alert), WEB_MIN_REPLICAS=1 to keep the site warm.
Then create the environment "production" (Settings → Environments) and run the Deploy workflow.
EOF
