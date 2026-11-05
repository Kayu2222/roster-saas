<#
Deletes everything this project created in Azure. Run from the project root:

    .\infra\teardown.ps1

Removes the whole resource group (app, database and all data, registry, Key Vault),
then purges the soft-deleted Key Vault so setup.ps1 can be run again cleanly later.
#>
param([string]$ResourceGroup = "rg-roster-saas")

$vault = az keyvault list --resource-group $ResourceGroup --query "[0].name" --output tsv

$answer = Read-Host "Delete resource group '$ResourceGroup' and ALL its data? Type the name to confirm"
if ($answer -ne $ResourceGroup) { Write-Host "Cancelled."; exit 1 }

Write-Host "Deleting $ResourceGroup (takes a few minutes)..."
az group delete --name $ResourceGroup --yes
if ($LASTEXITCODE -ne 0) { Write-Host "az group delete failed." -ForegroundColor Red; exit 1 }

if ($vault) {
    Write-Host "Purging soft-deleted Key Vault $vault..."
    az keyvault purge --name $vault
}
Write-Host "Done. Nothing from this project is left running in Azure."
