# Run both scripts: job-tracker then add_role_and_sort
Push-Location $PSScriptRoot
python .\job-tracker.py
python .\add_role_and_sort.py
Pop-Location
