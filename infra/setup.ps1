<#
One-time Azure setup for Roster SaaS. Run from the project root, signed in with `az login`:

    .\infra\setup.ps1

What it does:
  1. Registers the Azure services this project uses (needed once per subscription).
  2. Creates the resource group.
  3. Generates the database password and JWT secret. They go straight into Key Vault
     and are never printed or saved to disk.
  4. Deploys the infrastructure (infra/main.bicep), then builds and pushes the first
     Docker image with your local Docker Desktop, then deploys the Container App.
  5. Prints the values GitHub Actions needs (identifiers only, no secrets).

Takes about 10-15 minutes, mostly waiting for PostgreSQL.
Re-running it is safe but rotates both secrets (everyone has to log in again).
#>
param(
    [string]$ResourceGroup = "rg-roster-saas",
    [string]$Location = "australiaeast",
    [string]$GithubRepo = "Kayu2222/roster-saas"
)

$ErrorActionPreference = "Stop"

function Invoke-Az {
    # Runs az and stops the script if it fails (az is not a PowerShell cmdlet, so failures don't throw on their own).
    $output = az @args
    if ($LASTEXITCODE -ne 0) { throw "Command failed: az $($args[0]) $($args[1])" }
    # Join lines so multi-line JSON parses as one document in Windows PowerShell 5.1.
    return ($output -join "`n")
}

function New-Secret([int]$Length = 40) {
    # Cryptographically random letters and digits. The fixed "Aa9" prefix guarantees the
    # upper/lower/digit mix PostgreSQL requires; letters and digits need no URL escaping.
    $chars = [char[]]"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    return "Aa9" + (-join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] }))
}

function Write-Step([string]$Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }

# --- 0. Checks ---------------------------------------------------------------
Write-Step "Checking tools"
$account = Invoke-Az account show --output json | ConvertFrom-Json
Write-Host "Subscription: $($account.name)"
docker info --format "{{.ServerVersion}}" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not running. Start it and try again." }

# --- 1. Resource providers ---------------------------------------------------
Write-Step "Registering Azure services (first time can take a few minutes)"
foreach ($ns in @("Microsoft.App", "Microsoft.OperationalInsights", "Microsoft.ContainerRegistry",
                  "Microsoft.DBforPostgreSQL", "Microsoft.KeyVault", "Microsoft.ManagedIdentity")) {
    Write-Host "  $ns"
    Invoke-Az provider register --namespace $ns --wait --output none | Out-Null
}

# --- 2. Resource group -------------------------------------------------------
Write-Step "Creating resource group $ResourceGroup in $Location"
Invoke-Az group create --name $ResourceGroup --location $Location --output none | Out-Null

# --- 3. Secrets --------------------------------------------------------------
$postgresPassword = New-Secret
$jwtSecret = New-Secret 64

$commonParams = @(
    "location=$Location",
    "githubRepo=$GithubRepo",
    "postgresAdminPassword=$postgresPassword",
    "jwtSecret=$jwtSecret"
)

# --- 4a. Infrastructure (everything except the app) ---------------------------
Write-Step "Deploying infrastructure: registry, PostgreSQL, Key Vault, identities (about 10 minutes)"
$infra = Invoke-Az deployment group create --resource-group $ResourceGroup --name "infra" `
    --template-file infra/main.bicep `
    --parameters @commonParams "deployApp=false" `
    --query properties.outputs --output json | ConvertFrom-Json

$registry = $infra.registryName.value
$loginServer = $infra.registryLoginServer.value
$image = "$loginServer/roster-saas:bootstrap"

# --- 4b. First image ---------------------------------------------------------
Write-Step "Building and pushing the first image to $loginServer"
Invoke-Az acr login --name $registry --output none | Out-Null
docker build -t $image .
if ($LASTEXITCODE -ne 0) { throw "docker build failed" }
docker push $image
if ($LASTEXITCODE -ne 0) { throw "docker push failed" }

# --- 4c. The app --------------------------------------------------------------
Write-Step "Deploying the Container App"
$out = Invoke-Az deployment group create --resource-group $ResourceGroup --name "app" `
    --template-file infra/main.bicep `
    --parameters @commonParams "deployApp=true" "containerImage=$image" `
    --query properties.outputs --output json | ConvertFrom-Json

# Secrets are no longer needed in this session.
Remove-Variable postgresPassword, jwtSecret, commonParams

# --- 5. GitHub Actions settings ------------------------------------------------
$vars = [ordered]@{
    AZURE_CLIENT_ID       = $out.githubClientId.value
    AZURE_TENANT_ID       = $out.tenantId.value
    AZURE_SUBSCRIPTION_ID = $out.subscriptionId.value
    AZURE_RESOURCE_GROUP  = $ResourceGroup
    ACR_NAME              = $out.registryName.value
    CONTAINER_APP_NAME    = $out.containerAppName.value
}

Write-Step "Done"
Write-Host "API:     $($out.appUrl.value)/docs" -ForegroundColor Green
Write-Host "(The first request after a quiet period takes a few seconds: the app scales to zero when idle.)"

if (Get-Command gh -ErrorAction SilentlyContinue) {
    Write-Step "Saving GitHub Actions variables with the GitHub CLI"
    foreach ($k in $vars.Keys) {
        gh variable set $k --body $vars[$k] --repo $GithubRepo
    }
} else {
    Write-Step "Add these as GitHub repository VARIABLES (not secrets; they are identifiers)"
    Write-Host "GitHub > $GithubRepo > Settings > Secrets and variables > Actions > Variables > New repository variable`n"
    foreach ($k in $vars.Keys) { Write-Host ("  {0,-22} {1}" -f $k, $vars[$k]) }
}
Write-Host "`nAfter that, every push to main is tested and deployed automatically."
