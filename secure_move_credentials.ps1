<#
Move credentials/token files into a hidden secure folder and set environment variables to point to them.
Usage (PowerShell as the user who will run the scheduled task):
.
# Run in PowerShell
.
# Example:
#   .\secure_move_credentials.ps1 -Files @('credentials.json','client_secret_69687429889-3l1a87v0m0ki7f6dktfjspid37om66t7.apps.googleusercontent.com.json','token_gmail.pickle','token_sheets.pickle')
#
# This script will move the files to %USERPROFILE%\.job_tracker_creds (hidden) and run setx to persist env vars.
# You must restart your shell (or log out/in) for setx changes to be available in new sessions.
# For scheduled tasks, configure the task to run as the same user or set the env vars in the task XML/Action.
#>
param(
    [string[]]$Files = @('credentials.json','client_secret_69687429889-3l1a87v0m0ki7f6dktfjspid37om66t7.apps.googleusercontent.com.json','token_gmail.pickle','token_sheets.pickle')
)

$home = [Environment]::GetFolderPath('UserProfile')
$dest = Join-Path $home '.job_tracker_creds'
if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest | Out-Null }

foreach ($f in $Files) {
    if (Test-Path $f) {
        $dst = Join-Path $dest (Split-Path $f -Leaf)
        Move-Item -Path $f -Destination $dst -Force
        Write-Host "Moved $f -> $dst"
        # create environment variable mapping
        $name = switch -WildCard ($f) {
            '*credentials.json' { 'CREDENTIALS_FILE' }
            '*client_secret*' { 'CREDENTIALS_FILE' }
            '*token_gmail*' { 'TOKEN_GMAIL_FILE' }
            '*token_sheets*' { 'TOKEN_SHEETS_FILE' }
            default { 'CREDENTIALS_FILE' }
        }
        # Persist env var for user
        setx $name $dst | Out-Null
        Write-Host "Set environment variable $name -> $dst (use new shell to see it)"
    } else {
        Write-Host "File not found: $f"
    }
}

Write-Host "All done. Restart PowerShell to pick up new environment variables (or re-open session)."