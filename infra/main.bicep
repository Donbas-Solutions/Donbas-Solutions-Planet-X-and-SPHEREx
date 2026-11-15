// SPHEREx Blink on Azure Container Apps: one app whose container runs nginx (public) and the FastAPI backend.
// Deployed by .github/workflows/deploy.yml in two passes: deployApps=false creates the registry, the images are
// pushed, then deployApps=true creates or updates the app with the new tag.

targetScope = 'resourceGroup'

param location string = resourceGroup().location
param prefix string = 'spherex-blink'
param deployApps bool = false
param imageTag string = 'latest'

@description('0 lets the app sleep when idle (a cold start pulls the ~900 MB image); 1 keeps it warm.')
@minValue(0)
@maxValue(1)
param minReplicas int = 0

param cpu string = '1.25'
param memory string = '2.5Gi'

@description('Monthly cost alert for this resource group; empty disables the budget.')
param budgetEmail string = ''
param budgetAmountUsd int = 20
@description('First day of a month; fixed because Azure refuses to move the start of an existing budget.')
param budgetStartDate string = '2026-11-01'

var suffix = uniqueString(resourceGroup().id)
var webName = '${prefix}-web'
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var tags = { app: prefix }

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    // Caps log ingestion so logs cannot eat the credit.
    workspaceCapping: { dailyQuotaGb: json('0.1') }
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: replace('${prefix}${suffix}', '-', '')
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

resource pullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-pull'
  location: location
  tags: tags
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, pullIdentity.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: pullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
  }
}

var webUrl = 'https://${webName}.${env.properties.defaultDomain}'
var registry = [{ server: acr.properties.loginServer, identity: pullIdentity.id }]
var identity = {
  type: 'UserAssigned'
  userAssignedIdentities: { '${pullIdentity.id}': {} }
}

// One container (infra/app.Dockerfile) with nginx and the backend, talking over localhost: the environment is an
// "express" one (properties.environmentMode, 2026-11-15), which allows a single container per app and has no
// internal-only ingress, so a separate backend app would be public and bypass nginx's method filter and rate limit.
resource app 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: webName
  location: location
  tags: tags
  identity: identity
  dependsOn: [acrPull]
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registry
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'app'
          image: '${acr.properties.loginServer}/${prefix}-app:${imageTag}'
          resources: { cpu: json(cpu), memory: memory }
          env: [
            { name: 'CORS_ORIGINS', value: webUrl }
            { name: 'PIPELINE_WORKERS', value: '1' }
            { name: 'MAX_RUNNING_JOBS', value: '1' }
            { name: 'IRSA_MAX_CONCURRENCY', value: '8' }
            // The container's ephemeral disk is a few GB.
            { name: 'RAW_CACHE_MAX_MB', value: '2000' }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/api/health', port: 8080 }
              periodSeconds: 5
              failureThreshold: 30
            }
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8080 }
              periodSeconds: 30
            }
          ]
        }
      ]
      // One replica at most: jobs and their progress live in the backend's memory.
      scale: {
        minReplicas: minReplicas
        maxReplicas: 1
        rules: [{ name: 'http', http: { metadata: { concurrentRequests: '100' } } }]
      }
    }
  }
}

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = if (!empty(budgetEmail)) {
  name: '${prefix}-monthly'
  properties: {
    category: 'Cost'
    amount: budgetAmountUsd
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actual80: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [budgetEmail]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [budgetEmail]
      }
    }
  }
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output webUrl string = webUrl
