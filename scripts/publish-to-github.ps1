# Windows PowerShell version of publish-to-github.sh (needs: gh auth login)
param([string]$Owner = "rogerwtrimble-tech", [string]$Repo = "nb_graph", [string]$Visibility = "private")
Set-Location (Join-Path $PSScriptRoot "..")
gh repo view "$Owner/$Repo" *> $null
if ($LASTEXITCODE -ne 0) { gh repo create "$Owner/$Repo" "--$Visibility" --description "Graph-first UI for NetBox on PostgreSQL 19" --disable-wiki }
git remote remove origin 2>$null
git remote add origin "https://github.com/$Owner/$Repo.git"
git push -u origin main
