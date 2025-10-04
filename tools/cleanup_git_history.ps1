<#
Detect and optionally remove sensitive files from the index/history.

This script does NOT automatically rewrite history. It helps you find files
that look like credentials/tokens and shows the git commands you can run.

If you already committed secrets, rotate/revoke them first. Then use BFG or
git-filter-repo to purge them from history and force-push the cleaned branch.
#>

param(
    [switch]$RemoveFromIndex
)

Write-Host "Scanning git for likely sensitive files..." -ForegroundColor Cyan

$patterns = @(
    'credentials.json',
    'client_secret_*.json',
    'token_gmail.pickle',
    'token_sheets.pickle',
    '.job_tracker_creds',
    '*.pem','*.key','*.crt'
)

$found = @()
foreach($p in $patterns){
    $matches = git ls-files -- "${p}" 2>$null
    if($matches){ $found += $matches }
}

if(-not $found){
    Write-Host "No tracked sensitive files found in the index." -ForegroundColor Green
    exit 0
}

Write-Host "Tracked sensitive files:" -ForegroundColor Yellow
$found | ForEach-Object { Write-Host " - $_" }

Write-Host "`nRecommended next steps (dry-run shown):" -ForegroundColor Cyan
Write-Host "1) Rotate/revoke any exposed credentials immediately (Google API keys, OAuth clients, etc.)."
Write-Host "2) Remove files from the index (keeps them locally):"
Write-Host "    git rm --cached <file>"
Write-Host "   Example: git rm --cached credentials.json"

Write-Host "3) Purge files from history using BFG or git-filter-repo and force-push." -ForegroundColor Yellow
Write-Host "   BFG example (after installing BFG):"
Write-Host "     bfg --delete-files 'credentials.json'"
Write-Host "     git reflog expire --expire=now --all && git gc --prune=now --aggressive"
Write-Host "     git push --force"

if($RemoveFromIndex){
    Write-Host "Removing found files from the index (git rm --cached)..." -ForegroundColor Red
    foreach($f in $found){
        git rm --cached --force -- "$f"
    }
    Write-Host "Files removed from index. Commit the removal and then run BFG or git-filter-repo to purge history." -ForegroundColor Green
}
